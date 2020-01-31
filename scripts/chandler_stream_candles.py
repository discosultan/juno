import asyncio
import logging

from juno import exchanges
from juno.asyncio import enumerate_async
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import HOUR_MS, MIN_MS, time_ms

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'
INTERVAL = MIN_MS
# Should fetch 2 historical and rest future.
NOW = floor_multiple(time_ms(), MIN_MS)
START = NOW - 2 * MIN_MS
END = START + HOUR_MS


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[client])
    async with client:
        start = floor_multiple(time_ms(), MIN_MS) - 2 * MIN_MS

        logging.info(f'start {start}')
        async for i, candle in enumerate_async(chandler.stream_candles(
            name, SYMBOL, INTERVAL, START, END, closed=False
        )):
            historical_or_future = 'future' if candle.time >= NOW else 'historical'
            logging.info(f'{historical_or_future} candle {i}: {candle}')
            assert candle.time == START + i * INTERVAL
            if candle.time < NOW:
                assert candle.closed

        logging.info('done')


asyncio.run(main())
