import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

SYMBOL = 'iota-btc'
MARGIN = False


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        orders = await client.list_orders(symbol=SYMBOL, margin=MARGIN)
        logging.info(orders)

asyncio.run(main())
