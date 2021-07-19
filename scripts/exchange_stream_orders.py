import asyncio
import logging

from juno.exchanges import Exchange

EXCHANGE = "binance"
SYMBOL = "iota-btc"


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as client:
        async with client.connect_stream_orders(symbol=SYMBOL) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
