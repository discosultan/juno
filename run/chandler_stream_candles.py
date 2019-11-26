import asyncio
import logging
import os

from juno import exchanges
from juno.components import Chandler, Trades
from juno.logging import create_handlers
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import HOUR_MS, MIN_MS, time_ms

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    sqlite = SQLite()
    client = EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    )
    name = name.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades, sqlite, [client])
    async with client:
        # Should fetch 2 historical and rest future.
        start = floor_multiple(time_ms(), MIN_MS) - 2 * MIN_MS
        end = start + HOUR_MS
        logging.info(f'start {start}')
        stream = chandler.stream_candles(name, SYMBOL, MIN_MS, start, end, closed=False)

        # Historical.
        candle = await stream.__anext__()
        logging.info(f'historical candle 1: {candle}')
        assert candle.closed
        assert candle.time == start
        # Historical.
        candle = await stream.__anext__()
        logging.info(f'historical candle 2: {candle}')
        assert candle.closed
        assert candle.time == start + 1 * MIN_MS
        # Future.
        candle = await stream.__anext__()
        logging.info(f'future candle 1: {candle}')
        assert candle.time == start + 2 * MIN_MS

        await stream.aclose()
        logging.info('all good')


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='DEBUG')
asyncio.run(main())
