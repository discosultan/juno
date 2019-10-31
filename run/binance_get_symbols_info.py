import asyncio
import logging
import os

from juno.exchanges import Binance


async def main():
    async with Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    ) as client:
        symbols_info = await client.get_symbols_info()
        logging.info(symbols_info.filters['ada-btc'])
        logging.info(symbols_info.filters.keys())


logging.basicConfig(level='DEBUG')
asyncio.run(main())
