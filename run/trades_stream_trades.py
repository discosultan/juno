import asyncio
import logging
import os

from juno import exchanges
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
        stream = trades.stream_trades(name, SYMBOL, start, end)

        for i in range(0, 2):
            trade = await stream.__anext__()
            logging.info(f'trade[{i}]: {trade}')

        await stream.aclose()
        logging.info('done')


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='INFO')
asyncio.run(main())
