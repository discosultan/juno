import asyncio
import logging

from juno import exchanges, storages
from juno.asyncio import enumerate_async
from juno.config import from_env, init_instance
from juno.time import strptimestamp
from juno.trades import Trades

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'eth-btc'


async def main() -> None:
    storage = storages.SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(storage, [client])
    async with client, trades:
        start = strptimestamp('2019-03-22T08:00')
        end = strptimestamp('2019-04-02T16:00')
        logging.info(f'start {start}; end {end}')

        async for i, trade in enumerate_async(trades.stream_trades(name, SYMBOL, start, end)):
            logging.info(f'trade[{i}]: {trade}')
            if i == 2:
                break


asyncio.run(main())
