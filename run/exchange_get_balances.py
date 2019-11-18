import asyncio
import logging
import os

from juno import exchanges
from juno.logging import create_handlers

EXCHANGE_TYPE = exchanges.Binance


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    async with EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    ) as client:
        balances = await client.get_balances()
        logging.info(balances)


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='INFO')
asyncio.run(main())
