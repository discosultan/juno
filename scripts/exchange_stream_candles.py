import asyncio
import logging

from juno import Interval_
from juno.exchanges import Exchange

EXCHANGE = "binance"


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        async with exchange.connect_stream_candles("eth-btc", Interval_.MIN) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
