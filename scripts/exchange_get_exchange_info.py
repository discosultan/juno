import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance


async def main():
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        exchange_info = await client.get_exchange_info()
        logging.info(exchange_info.filters['ada-btc'])
        logging.info(exchange_info.filters.keys())
        logging.info(exchange_info.candle_intervals)


asyncio.run(main())
