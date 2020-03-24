import asyncio
import logging
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

ASSET = 'btc'
SIZE = None
REPAY = True


async def main() -> None:
    size = SIZE
    async with init_instance(Binance, from_env()) as client:
        if REPAY:
            if size is None:
                balance = (await client.get_balances(margin=True))[ASSET]
                size = balance.borrowed + balance.interest
            await client.repay(ASSET, size)
        else:
            if size is None:
                size = Decimal('0.0000_0001')
            await client.borrow(ASSET, size)
        logging.info(f'{"repaid" if REPAY else "borrowed"} {size} {ASSET}')

asyncio.run(main())
