import asyncio
import logging

from juno import exchanges
from juno.config import config_from_env, init_instance

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'ada-eur'


async def main():
    async with init_instance(EXCHANGE_TYPE, config_from_env()) as client:
        async with client.connect_stream_orders() as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
