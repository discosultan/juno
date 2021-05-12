import argparse
import asyncio
import csv
import logging

import juno.json as json
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.time import strftimestamp

parser = argparse.ArgumentParser()
parser.add_argument(
    '--dump',
    action='store_true',
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        deposits, withdrawals = await asyncio.gather(
            client.list_deposit_history(),
            client.list_withdraw_history(),
        )

    transfers = []
    for deposit in deposits:
        status = deposit_status(deposit['status'])
        if status == 'success':
            transfers.append({
                'time': timestamp(deposit['insertTime']),
                'type': 'deposit',
                'amount': deposit['amount'],
                'currency': deposit['coin'],
            })
    for withdrawal in withdrawals:
        status = withdraw_status(withdrawal['status'])
        if status == 'completed':
            transfers.append({
                'time': withdrawal['applyTime'],
                'type': 'withdrawal',
                'amount': withdrawal['amount'],
                'currency': withdrawal['coin'],
            })
    # Sort by time ascending.
    transfers.sort(key=lambda r: r['time'])

    logging.info(json.dumps(transfers, 4))

    if args.dump:
        with open('crypto_transfers.csv', 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, ['time', 'type', 'amount', 'currency'])
            writer.writeheader()
            writer.writerows(transfers)


def timestamp(value: int) -> str:
    return strftimestamp(value)[0:-6]


def deposit_status(value: int) -> str:
    if value == 0:
        return 'pending'
    if value == 6:
        return 'credited but cannot withdraw'
    if value == 1:
        return 'success'
    raise NotImplementedError()


def withdraw_status(value: int) -> str:
    if value == 0:
        return 'email sent'
    if value == 1:
        return 'cancelled'
    if value == 2:
        return 'awaiting approval'
    if value == 3:
        return 'rejected'
    if value == 4:
        return 'processing'
    if value == 5:
        return 'failure'
    if value == 6:
        return 'completed'
    raise NotImplementedError()


def transfer_type(value: int) -> str:
    if value == 0:
        return 'external'
    if value == 1:
        return 'internal'
    raise NotImplementedError()


asyncio.run(main())
