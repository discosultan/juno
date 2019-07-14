import asyncio
import logging
import os

from juno.exchanges import Binance
from juno.math import floor_multiple
from juno.time import HOUR_MS, MIN_MS, time_ms


async def main():
    async with Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    ) as client:
        # Should fetch 1 historical and rest future.
        start = floor_multiple(time_ms(), MIN_MS) - 2 * MIN_MS
        end = start + HOUR_MS
        logging.critical(f'start {start}')
        async with client.connect_stream_candles('eth-btc', MIN_MS, start, end) as stream:
            # Historical.
            candle = await stream.asend(None)
            logging.critical(f'candle1 {candle.time} == {start}')
            assert candle.closed
            assert candle.time == start
            # Historical.
            candle = await stream.asend(None)
            logging.critical(f'candle2 {candle.time} == {start + 1 * MIN_MS}')
            assert candle.closed
            assert candle.time == start + 1 * MIN_MS
            # Future.
            candle = await stream.asend(None)
            logging.critical(f'candle3 {candle.time} == {start + 2 * MIN_MS}')
            assert not candle.closed
            assert candle.time == start + 2 * MIN_MS
            logging.critical('all good')


logging.basicConfig(level='DEBUG')
asyncio.run(main())
