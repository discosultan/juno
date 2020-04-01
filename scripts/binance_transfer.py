import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

ASSET = 'btc'
SIZE = None
MARGIN = False


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        size = SIZE
        if not size:
            balances = await client.get_balances(margin=not MARGIN)
            size = balances[ASSET].available
        await client.transfer(asset=ASSET, size=size, margin=MARGIN)
        logging.info(f'transferred {size} {ASSET} to {"margin" if MARGIN else "spot"} account')

asyncio.run(main())
