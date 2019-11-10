import asyncio
import logging
import os

from juno import exchanges
from juno.logging import create_handlers

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'btc-eur'


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    async with EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    ) as client:
        async with client.connect_stream_trades(symbol=SYMBOL) as stream:
            i = 0
            async for val in stream:
                logging.info(val)
                i += 1
                if i == 2:
                    break


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='DEBUG')
asyncio.run(main())
