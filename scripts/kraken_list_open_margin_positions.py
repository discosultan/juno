import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Kraken


async def main() -> None:
    async with init_instance(Kraken, from_env()) as exchange:
        assert isinstance(exchange, Kraken)
        logging.info(await exchange.list_open_margin_positions())


asyncio.run(main())
