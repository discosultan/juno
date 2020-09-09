import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Coinbase


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        exchange_info = await client.get_exchange_info()
        logging.info(exchange_info.filters['btc-eur'])
        logging.info(exchange_info.filters.keys())


asyncio.run(main())
