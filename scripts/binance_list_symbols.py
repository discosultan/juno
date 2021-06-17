import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        logging.info(await exchange.list_symbols(isolated=True))


asyncio.run(main())
