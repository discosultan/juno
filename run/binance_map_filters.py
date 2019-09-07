import asyncio
import logging
import os

from juno.exchanges import Binance


async def main():
    async with Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    ) as client:
        fees = await client.map_filters()
        logging.info(fees['ada-btc'])


logging.basicConfig(level='DEBUG')
asyncio.run(main())
