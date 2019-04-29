import asyncio
import logging
import os

from juno.exchanges import Binance
from juno.time import HOUR_MS, MIN_MS, time_ms


async def main():
    async with Binance(os.environ['JUNO__BINANCE__API_KEY'],
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as client:
        start = time_ms()
        end = start + HOUR_MS
        async for _, _ in client.stream_candles('eth-btc', MIN_MS, start, end):
            pass


logging.basicConfig(level='DEBUG')
asyncio.run(main())
