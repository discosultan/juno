import asyncio
import logging
import os
import sys

from juno.exchanges import Binance

ORDER_ID = 0
SYMBOL = 'ada-btc'


async def main() -> None:
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    async with binance:
        res = await binance.cancel_order(symbol=SYMBOL, id_=ORDER_ID)
        logging.info(res)
    logging.info('Done!')


logging.basicConfig(
    handlers=[logging.StreamHandler(stream=sys.stdout)],
    level='INFO')
asyncio.run(main())
