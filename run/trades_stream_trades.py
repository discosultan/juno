import asyncio
import logging
import os

from juno import exchanges, storages
from juno.asyncio import enumerate_async
from juno.components import Trades
from juno.logging import create_handlers
from juno.time import strptimestamp

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'eth-btc'


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    storage = storages.SQLite()
    client = EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    )
    name = name.lower()
    trades = Trades(storage, [client])
    async with client:
        start = strptimestamp('2019-03-22T08:00')
        end = strptimestamp('2019-04-02T16:00')
        logging.info(f'start {start}; end {end}')

        async for i, trade in enumerate_async(trades.stream_trades(name, SYMBOL, start, end)):
            logging.info(f'trade[{i}]: {trade}')
            if i == 2:
                break

        logging.info('done')


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='DEBUG')
asyncio.run(main(), debug=True)
