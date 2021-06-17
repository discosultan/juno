import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('-a', '--account', default='spot')
parser.add_argument('-s', '--symbol', default=None)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        orders = await exchange.list_orders(account=args.account, symbol=args.symbol)
        logging.info(orders)


asyncio.run(main())
