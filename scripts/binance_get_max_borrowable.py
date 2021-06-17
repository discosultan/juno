import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('account', nargs='?', default='margin')
parser.add_argument('asset', nargs='?', default='eth')
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        max_borrowable = await exchange.get_max_borrowable(asset=args.asset, account=args.account)
        logging.info(f'max borrowable {max_borrowable} {args.asset}')


asyncio.run(main())
