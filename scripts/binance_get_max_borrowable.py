import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('asset', nargs='?', default='eth')
parser.add_argument('-a', '--account', default='margin')
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        max_borrowable = await client.get_max_borrowable(asset=args.asset, account=args.account)
        logging.info(f'max borrowable {max_borrowable} {args.asset}')


asyncio.run(main())
