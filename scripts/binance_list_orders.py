import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument(
    '-m', '--margin',
    action='store_true',
    default=False,
    help='if set, use margin; otherwise spot account',
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        orders = await client.list_orders(symbol=args.symbol, margin=args.margin)
        logging.info(orders)

asyncio.run(main())
