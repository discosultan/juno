import asyncio
import logging

from juno.exchanges import Exchange
from juno.time import MIN_MS

EXCHANGE = "binance"


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        async with exchange.connect_stream_candles("eth-btc", MIN_MS) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
