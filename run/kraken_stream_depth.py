import asyncio
import logging
import os

from juno.exchanges import Kraken


async def main():
    async with Kraken(
        os.environ['JUNO__KRAKEN__API_KEY'], os.environ['JUNO__KRAKEN__SECRET_KEY']
    ) as client:
        async with client.connect_stream_depth('ada-eur') as stream:
            async for balance in stream:
                logging.info(balance)


logging.basicConfig(level='INFO')
asyncio.run(main())
