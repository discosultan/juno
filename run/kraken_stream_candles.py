import asyncio
import logging
import os

from juno.exchanges import Kraken
from juno.time import MIN_MS


async def main():
    async with Kraken(
        os.environ['JUNO__KRAKEN__API_KEY'], os.environ['JUNO__KRAKEN__SECRET_KEY']
    ) as client:
        async with client.connect_stream_candles('btc-eur', MIN_MS) as stream:
            async for val in stream:
                logging.info(val)


logging.basicConfig(level='INFO')
asyncio.run(main())
