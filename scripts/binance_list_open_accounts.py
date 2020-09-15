import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        logging.info(await client.list_open_accounts())


asyncio.run(main())
