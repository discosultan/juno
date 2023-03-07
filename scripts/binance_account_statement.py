# This script expects as an input Binance transaction history. To get that:
# 1. Go to https://www.binance.com/en/my/wallet/history/deposit-crypto.
# 2. Click on "Generate all statements".
# 3. Choose a time range.
# 4. Ensure account is "All".
# 5. Ensure coin is "All".
# 6. Ensure sub-account is "None".
# 7. Ensure "Hide transfer record" is ticked.

import argparse
import asyncio
import csv
import logging
import os
import os.path
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, TypedDict

from juno import Asset, Timestamp, Timestamp_, json
from juno.components.chandler import Chandler
from juno.components.informant import Informant
from juno.components.prices import Prices
from juno.exchanges.exchange import Exchange
from juno.storages.sqlite import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("--dir", help="Path to directory containing Binance transactions CSV files.")
parser.add_argument("--date", type=Timestamp_.parse, help="The date of the account statement.")
parser.add_argument(
    "--dump",
    action="store_true",
    default=False,
)
parser.add_argument("--name", default=None, help="Optional name to put on the account statement.")
parser.add_argument(
    "--user-id",
    default=None,
    help="Optional user ID to put on the account statement.",
)
parser.add_argument(
    "--account-date",
    default=None,
    type=Timestamp_.parse,
    help="Optional date the account was opened to put on the account statement.",
)
parser.add_argument(
    "--threshold",
    type=Decimal,
    default=Decimal("0.01"),
    help="Minimum EUR value threshold to be included. Defaults to 0.01.",
)
args = parser.parse_args()

btc_precision = Decimal("0.00000001")
eur_precision = Decimal("0.01")
prices_exchange = "binance"


class TransactionRow(TypedDict):
    User_ID: str
    UTC_Time: str
    Account: str
    Operation: str
    Coin: str
    Change: str
    Remark: str


@dataclass
class Transaction:
    time: Timestamp
    asset: Asset
    change: Decimal


@dataclass
class Balance:
    asset: Asset
    amount: Decimal
    btc_value: Decimal
    eur_value: Decimal
    btc_rate: Decimal


async def main() -> None:
    # Read input data.
    paths = os.listdir(args.dir)
    transactions: list[Transaction] = []
    for path in (path for path in paths if path.endswith(".csv")):
        with open(os.path.join(args.dir, path), mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            # Convert to domain model.
            file_transactions = (to_transaction(row) for row in reader)  # type: ignore
            # Exclude if transaction past statement date.
            file_transactions = (tx for tx in file_transactions if tx.time <= args.date)
            transactions.extend(file_transactions)

    # Sort by time.
    transactions.sort(key=lambda x: x.time)

    # Calculate balances.
    asset_balances: dict[str, Decimal] = defaultdict(lambda: Decimal("0.0"))
    for transaction in transactions:
        # Add savings balances prefixed with `ld*` to their non-savings counterparts.
        asset = transaction.asset
        if len(asset) >= 5 and asset.startswith("ld"):
            asset = asset[2:]
        asset_balances[asset] += transaction.change

    # Find prices for date.
    storage = SQLite()
    exchange = Exchange.from_env(prices_exchange)
    informant = Informant(storage, [exchange])
    chandler = Chandler(storage, [exchange])
    prices = Prices(informant, chandler)
    async with exchange, storage, informant, chandler, prices:
        asset_btc_prices, btc_eur_prices = await asyncio.gather(
            prices.map_asset_prices_for_timestamp(
                exchange=prices_exchange,
                assets=set(asset_balances.keys()),
                time=args.date,
                target_asset="btc",
                ignore_missing_price=True,
            ),
            prices.map_asset_prices_for_timestamp(
                exchange=prices_exchange,
                assets={"btc"},
                time=args.date,
                target_asset="eur",
            ),
        )

    # Calculate final balances.
    btc_eur_rate = btc_eur_prices["btc"]
    final_balances = [
        Balance(
            asset=asset,
            amount=amount,
            btc_rate=(btc_rate := asset_btc_prices[asset]),
            btc_value=(btc_value := amount * btc_rate),
            eur_value=btc_value * btc_eur_rate,
        )
        for asset, amount in asset_balances.items()
    ]

    # Warn on missing prices.
    missing_prices = {
        balance.asset: balance.amount for balance in final_balances if balance.btc_value.is_nan()
    }
    if missing_prices:
        logging.warning(f"Missing prices for: {missing_prices}")

    # Output.
    if args.dump:
        generate_statement(final_balances, btc_eur_rate)
    else:
        log_info_json(list(map(asdict, final_balances)))


def to_transaction(row: TransactionRow) -> Transaction:
    return Transaction(
        time=Timestamp_.parse(row["UTC_Time"]),
        asset=row["Coin"].lower(),
        change=Decimal(row["Change"]),
    )


def log_info_json(value: Any) -> None:
    logging.info(json.dumps(value, indent=4))


def generate_statement(
    balances: list[Balance],
    btc_eur_rate: Decimal,
) -> None:
    lines = [
        "Binance Account Statement",
    ]

    if args.name:
        lines.extend(["", "Attention:", args.name])

    name = args.name if args.name else "the person"
    user_id = f" {args.user_id}" if args.user_id else ""
    account_date = (
        f" This account was opened on {format_timestamp(args.account_date)}."
        if args.account_date
        else ""
    )
    lines.extend(
        [
            "",
            f"This letter confirms that {name} maintains an individual trading account"
            f"{user_id} with Binance.com.{account_date}",
        ]
    )

    lines.extend(
        [
            "",
            "The aforementioned account has the summarized asset balances of the main account "
            f"detailed below as at {format_timestamp(Timestamp_.now())}, distinguished by "
            "available crypto-asset tokens.",
        ]
    )

    headers = ["Date", "User ID", "Account Type", "Wallet", "Rate"]
    values = [
        format_timestamp(args.date),
        args.user_id,
        "MasterAccount",
        "All",
        f"BTC 1 = EUR {btc_eur_rate.quantize(eur_precision)}",
    ]
    lines.extend(format_overview(headers, values))

    total_btc_value = sum(
        (
            balance.btc_value
            for balance in balances
            if not balance.eur_value.is_nan() and balance.eur_value >= args.threshold
        ),
        Decimal("0.0"),
    ).quantize(btc_precision)
    total_eur_value = sum(
        (
            balance.eur_value
            for balance in balances
            if not balance.eur_value.is_nan() and balance.eur_value >= args.threshold
        ),
        Decimal("0.0"),
    ).quantize(eur_precision)
    lines.extend(
        [
            "",
            "Total Value",
            f"BTC {format_decimal(total_btc_value)} = EUR {total_eur_value}",
        ]
    )

    lines.extend(
        [
            "",
            "Assets",
        ]
    )
    lines.extend(
        [
            f"{balance.asset.upper()} {balance.amount} = BTC "
            f"{format_decimal(balance.btc_value.quantize(btc_precision))} = EUR "
            f"{balance.eur_value.quantize(eur_precision)}"
            for balance in balances
            if not balance.eur_value.is_nan() and balance.eur_value >= args.threshold
        ]
    )

    with open(get_filename(), "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def get_filename() -> str:
    name = ""
    if args.name:
        name += "_".join(args.name.split()).lower() + "_"
    name += "binance"
    name += "_" + format_timestamp(args.date).replace("-", "_")
    name += ".txt"
    return name


def format_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f"{value:f}"


def format_timestamp(value: Timestamp) -> str:
    # 2020-01-01T00:00:00.000000+00:00 -> 2020-01-01
    return Timestamp_.format(value)[:10]


def format_overview(headers: list[str], values: list[str]) -> list[str]:
    row_format = "    ".join(
        "{:<" + str(max(len(header), len(value))) + "}" for header, value in zip(headers, values)
    )
    return [
        "",
        "Overview",
        row_format.format(*headers),
        row_format.format(*values),
    ]


asyncio.run(main())
