import asyncio
import logging
import os

from juno.exchanges import Binance
from juno.logging import create_handlers
from juno.time import MIN_MS


async def main():
    async with Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    ) as client:
        async with client.connect_stream_candles('eth-btc', MIN_MS) as stream:
            async for candle in stream:
                logging.info(candle)


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level='INFO')
asyncio.run(main())
