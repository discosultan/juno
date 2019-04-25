import asyncio
import logging
import os
from decimal import Decimal

from juno import OrderType, Side
from juno.exchanges import Binance


async def main():
    async with Binance(os.environ['JUNO__BINANCE__API_KEY'],
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as exchange:
        res = await exchange.place_order(
            symbol='eth-btc',
            side=Side.BUY,
            type_=OrderType.MARKET,
            size=Decimal(1),
            test=True)
        logging.info(res)


logging.basicConfig(level='DEBUG')
asyncio.run(main())
