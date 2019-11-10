import asyncio
import logging
import os

from juno import exchanges
from juno.asyncio import enumerate_async
from juno.logging import create_handlers
from juno.time import time_ms, MIN_MS, SEC_MS

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'btc-eur'


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    async with EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    ) as client:
        start = time_ms() - MIN_MS
        end = start + MIN_MS + SEC_MS
        async for i, val in enumerate_async(
            client.stream_historical_trades(symbol=SYMBOL, start=start, end=end)
        ):
            logging.info(val)
            if i == 2:
                break


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='DEBUG')
asyncio.run(main())
