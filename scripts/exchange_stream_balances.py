import argparse
import asyncio
import logging

from juno import AccountType
from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument(
    'account',
    nargs='?',
    type=lambda s: AccountType[s.upper()],
    default=AccountType.SPOT,
)
parser.add_argument('isolated_symbol', nargs='?', default=None)
args = parser.parse_args()


async def main() -> None:
    logging.info(f'streaming balances from {args.account.name} account')
    async with init_instance(Binance, from_env()) as client:
        async with client.connect_stream_balances(
            account=args.account, isolated_symbol=args.isolated_symbol
        ) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
