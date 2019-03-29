import asyncio
import logging
import os

from juno.exchanges import Binance


async def main():
    async with Binance(os.environ['JUNO__BINANCE__API_KEY'],
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as client:
        async for x in client.stream_balances():
            print(x)


logging.basicConfig(level='DEBUG')
asyncio.run(main())
