import asyncio
import logging
import os

from juno import exchanges
from juno.asyncio import enumerate_async
from juno.components import Trades
from juno.logging import create_handlers
from juno.storages import SQLite
from juno.time import MIN_MS, SEC_MS, time_ms

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'btc-eur'


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    sqlite = SQLite()
    client = EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    )
    name = name.lower()
    trades = Trades(sqlite, [client])
    async with client:
        start = time_ms() - MIN_MS
        end = start + MIN_MS + SEC_MS
        logging.info(f'start {start}')

        async for i, trade in enumerate_async(trades.stream_trades(name, SYMBOL, start, end)):
            logging.info(f'trade[{i}]: {trade}')
            if i == 2:
                break

        logging.info('done')


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='DEBUG')
asyncio.run(main(), debug=True)
