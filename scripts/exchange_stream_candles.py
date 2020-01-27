import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance
from juno.time import MIN_MS

EXCHANGE_TYPE = exchanges.Binance


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        async with client.connect_stream_candles('eth-btc', MIN_MS) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
