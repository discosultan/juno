import asyncio
import logging
from contextlib import AsyncExitStack

from juno import exchanges
from juno.components import Informant
from juno.config import config_from_env, init_instance
from juno.storages import SQLite

EXCHANGE_TYPES = [exchanges.Binance, exchanges.Coinbase, exchanges.Kraken]


async def main():
    storage = SQLite()
    config = config_from_env()
    exchanges = [init_instance(e, config) for e in EXCHANGE_TYPES]
    informant = Informant(storage, exchanges)
    async with AsyncExitStack() as stack:
        await asyncio.gather(*(stack.enter_async_context(e) for e in exchanges))
        async with informant:
            for exchange in EXCHANGE_TYPES:
                logging.info(exchange.__name__)
                logging.info(informant.list_symbols(exchange.__name__.lower()))
    logging.info('done')


asyncio.run(main())
