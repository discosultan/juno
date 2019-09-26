import asyncio
import logging
import os

from juno.components import Chandler
from juno.exchanges import Binance
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import HOUR_MS, MIN_MS, time_ms


async def main():
    sqlite = SQLite()
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    chandler = Chandler(sqlite, [binance])
    async with binance:
        # Should fetch 2 historical and rest future.
        start = floor_multiple(time_ms(), MIN_MS) - 2 * MIN_MS
        end = start + HOUR_MS
        logging.info(f'start {start}')
        stream = chandler.stream_candles('binance', 'eth-btc', MIN_MS, start, end, closed=False)

        # Historical.
        candle = await stream.asend(None)
        logging.info(f'candle1 {candle.time} == {start}')
        assert candle.closed
        assert candle.time == start
        # Historical.
        candle = await stream.asend(None)
        logging.info(f'candle2 {candle.time} == {start + 1 * MIN_MS}')
        assert candle.closed
        assert candle.time == start + 1 * MIN_MS
        # Future.
        candle = await stream.asend(None)
        logging.info(f'candle3 {candle.time} == {start + 2 * MIN_MS}')
        assert not candle.closed
        assert candle.time == start + 2 * MIN_MS
        logging.info('all good')


logging.basicConfig(level='DEBUG')
asyncio.run(main())
