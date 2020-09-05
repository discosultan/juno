import asyncio
import logging
from decimal import Decimal

from juno import OrderType, Side, exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
TEST = False
SIDE = Side.BUY
SYMBOL = 'eth-btc'
ORDERTYPE = OrderType.LIMIT_MAKER
SIZE = Decimal('0.2')
QUOTE = None
PRICE = Decimal('0.04')


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as exchange:
        res = await exchange.place_order(
            account='spot',
            symbol=SYMBOL,
            side=SIDE,
            type_=ORDERTYPE,
            price=PRICE,
            quote=QUOTE,
            size=SIZE,
            test=TEST,
        )
        logging.info(res)


asyncio.run(main())
