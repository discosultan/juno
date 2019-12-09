import asyncio
import logging
import os

from juno import exchanges

EXCHANGE_TYPE = exchanges.Binance


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    async with EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    ) as client:
        exchange_info = await client.get_exchange_info()
        logging.info(exchange_info.filters['ada-btc'])
        logging.info(exchange_info.filters.keys())
        logging.info(exchange_info.candle_intervals)


asyncio.run(main())
