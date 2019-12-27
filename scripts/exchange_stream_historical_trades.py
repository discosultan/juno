import asyncio
import logging

from juno import exchanges
from juno.asyncio import enumerate_async
from juno.config import config_from_env, init_instance
from juno.time import MIN_MS, SEC_MS, time_ms

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'btc-eur'


async def main():
    async with init_instance(EXCHANGE_TYPE, config_from_env()) as client:
        start = time_ms() - MIN_MS
        end = start + MIN_MS + SEC_MS
        async for i, val in enumerate_async(
            client.stream_historical_trades(symbol=SYMBOL, start=start, end=end)
        ):
            logging.info(val)
            if i == 2:
                break


asyncio.run(main())
