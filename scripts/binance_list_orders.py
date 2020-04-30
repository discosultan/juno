import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

SYMBOL = 'eth-btc'
MARGIN = False

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default=SYMBOL)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        orders = await client.list_orders(symbol=args.symbol, margin=MARGIN)
        logging.info(orders)

asyncio.run(main())
