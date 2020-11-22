import argparse
import asyncio
import logging

from juno.components import Orderbook
from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('symbols', type=lambda s: s.split(','))
parser.add_argument('--cycles', type=int, default=1)
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    orderbook = Orderbook([exchange])
    async with exchange, orderbook:
        await asyncio.gather(*(process(orderbook, s) for s in args.symbols))


async def process(orderbook: Orderbook, symbol: str) -> None:
    for i in range(args.cycles):
        logging.info(f'{symbol} cycle {i}')
        async with orderbook.sync('binance', symbol) as ctx:
            await ctx.updated.wait()


asyncio.run(main())
