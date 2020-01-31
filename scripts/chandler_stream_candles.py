import asyncio
import logging

from juno import exchanges, time
from juno.asyncio import enumerate_async
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import time_ms

# EXCHANGE_TYPE = exchanges.Binance
# SYMBOL = 'eth-btc'
# INTERVAL = time.MIN_MS
# # Should fetch 2 historical and rest future.
# START = floor_multiple(time_ms(), INTERVAL) - 2 * INTERVAL
# END = START + time.HOUR_MS

EXCHANGE_TYPE = exchanges.Coinbase
SYMBOL = 'btc-eur'
INTERVAL = time.DAY_MS
# Should fetch 2 historical and rest future.
START = time.strptimestamp('2018-01-01')
END = time.strptimestamp('2020-01-01')


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[client])
    now = floor_multiple(time_ms(), INTERVAL)
    async with client:
        logging.info(f'start {START}')
        async for i, candle in enumerate_async(chandler.stream_candles(
            name, SYMBOL, INTERVAL, START, END, closed=False
        )):
            historical_or_future = 'future' if candle.time >= now else 'historical'
            logging.info(f'{historical_or_future} candle {i}: {candle}')
            assert candle.time == START + i * INTERVAL
            if candle.time < now:
                assert candle.closed
            else:
                break

        logging.info('done')


asyncio.run(main())
