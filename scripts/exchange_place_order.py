import asyncio
import logging
from decimal import Decimal

from juno import OrderType, Side, exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Coinbase
TEST = False
SIDE = Side.BUY
SYMBOL = 'btc-eur'
ORDERTYPE = OrderType.MARKET
# SIZE = Decimal('0.0001')
SIZE = None
QUOTE = Decimal('10.0')
# QUOTE = None


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as exchange:
        res = await exchange.place_order(
            symbol=SYMBOL,
            side=SIDE,
            type_=ORDERTYPE,
            size=SIZE,
            quote=QUOTE,
            test=TEST,
        )
        logging.info(res)


asyncio.run(main())
