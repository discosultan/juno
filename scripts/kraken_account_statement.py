import argparse
import asyncio
import csv
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, TypedDict

from juno import Asset, Timestamp, Timestamp_, json
from juno.components.chandler import Chandler
from juno.components.informant import Informant
from juno.components.prices import Prices
from juno.components.trades import Trades
from juno.exchanges import kraken
from juno.exchanges.exchange import Exchange
from juno.storages.sqlite import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("--file", help="Path to CSV file containing Kraken ledger statements.")
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
    "--threshold",
    type=Decimal,
    default=Decimal("0.01"),
    help="Minimum EUR value threshold to be included. Defaults to 0.01.",
)
args = parser.parse_args()

btc_precision = Decimal("0.00000001")
eur_precision = Decimal("0.01")
prices_exchange = "kraken"


class TransactionRow(TypedDict):
    txid: str
    refid: str
    time: str
    type: str
    subtype: str
    aclass: str
    asset: str
    amount: str
    fee: str
    balance: str


@dataclass
class Transaction:
    time: Timestamp
    asset: Asset
    balance: Decimal


@dataclass
class Balance:
    asset: Asset
    amount: Decimal
    btc_value: Decimal
    eur_value: Decimal
    btc_rate: Decimal


async def main() -> None:
    # Read input data.
    with open(args.file, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        # Convert to domain model.
        file_transactions = (to_transaction(row) for row in reader if row["txid"])  # type: ignore
        # Exclude if transaction past statement date.
        file_transactions = (tx for tx in file_transactions if tx.time <= args.date)
        transactions = list(file_transactions)

    # Sort by time.
    transactions.sort(key=lambda x: x.time)

    # Find balances by taking the last asset entry before target date.
    transactions_grouped_by_asset: dict[Asset, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        transactions_grouped_by_asset[tx.asset].append(tx)
    asset_balances = {
        asset: txs[-1].balance for asset, txs in transactions_grouped_by_asset.items()
    }

    # Find prices for date.
    storage = SQLite()
    exchange = Exchange.from_env(prices_exchange)
    informant = Informant(storage, [exchange])
    trades = Trades(storage, [exchange])
    chandler = Chandler(storage, [exchange], trades=trades)
    prices = Prices(informant, chandler)
    async with exchange, storage, informant, trades, chandler, prices:
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
        time=Timestamp_.parse(row["time"]),
        asset=kraken._from_asset(row["asset"]),
        balance=Decimal(row["balance"]),
    )


def log_info_json(value: Any) -> None:
    logging.info(json.dumps(value, indent=4))


def generate_statement(
    balances: list[Balance],
    btc_eur_rate: Decimal,
) -> None:
    lines = [
        "Kraken Account Statement",
    ]

    if args.name:
        lines.extend(["", "Attention:", args.name])

    name = args.name if args.name else "the person"
    user_id = f" {args.user_id}" if args.user_id else ""
    lines.extend(
        [
            "",
            f"This letter confirms that {name} maintains an individual trading account"
            f"{user_id} with Kraken.com.",
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

    headers = ["Date", "User ID", "Rate"]
    values = [
        format_timestamp(args.date),
        args.user_id,
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
    name += "kraken"
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
