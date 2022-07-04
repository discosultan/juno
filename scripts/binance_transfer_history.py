import argparse
import asyncio
import csv
import logging

from juno import json
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.time import strftimestamp, strptimestamp

parser = argparse.ArgumentParser()
parser.add_argument(
    "--end",
    type=strptimestamp,
    default=None,
)
parser.add_argument(
    "--dump",
    action="store_true",
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        raw_deposits, raw_withdrawals = await asyncio.gather(
            exchange.list_deposit_history(end=args.end),
            exchange.list_withdraw_history(end=args.end),
        )
    raw_deposits.sort(key=lambda x: x["insertTime"])
    raw_withdrawals.sort(key=lambda x: x["applyTime"])

    deposits = []
    for deposit in raw_deposits:
        status = deposit_status(deposit["status"])
        deposits.append(
            {
                "Date(UTC)": timestamp(deposit["insertTime"]),
                "Amount": deposit["amount"],
                "Coin": deposit["coin"],
                "Status": status,
                "Transaction ID": deposit["txId"],
            }
        )

    withdrawals = []
    for withdrawal in raw_withdrawals:
        status = withdraw_status(withdrawal["status"])
        withdrawals.append(
            {
                "Date(UTC)": withdrawal["applyTime"],
                "Amount": withdrawal["amount"],
                "Coin": withdrawal["coin"],
                "Status": status,
                "Fee": withdrawal["transactionFee"],
                "Transaction ID": withdrawal["txId"],
            }
        )

    logging.info("DEPOSITS")
    logging.info(json.dumps(deposits, 4))
    logging.info("WITHDRAWALS")
    logging.info(json.dumps(withdrawals, 4))

    if args.dump:
        with open("crypto_deposits.csv", "w", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                ["Date(UTC)", "Amount", "Coin", "Status", "Transaction ID"],
            )
            writer.writeheader()
            writer.writerows(deposits)

        with open("crypto_withdrawals.csv", "w", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                ["Date(UTC)", "Amount", "Coin", "Status", "Fee", "Transaction ID"],
            )
            writer.writeheader()
            writer.writerows(withdrawals)


def timestamp(value: int) -> str:
    return strftimestamp(value)[0:-6]


def deposit_status(value: int) -> str:
    if value == 0:
        return "pending"
    if value == 6:
        return "credited but cannot withdraw"
    if value == 1:
        return "success"
    raise NotImplementedError()


def withdraw_status(value: int) -> str:
    if value == 0:
        return "email sent"
    if value == 1:
        return "cancelled"
    if value == 2:
        return "awaiting approval"
    if value == 3:
        return "rejected"
    if value == 4:
        return "processing"
    if value == 5:
        return "failure"
    if value == 6:
        return "completed"
    raise NotImplementedError()


def transfer_type(value: int) -> str:
    if value == 0:
        return "external"
    if value == 1:
        return "internal"
    raise NotImplementedError()


asyncio.run(main())
