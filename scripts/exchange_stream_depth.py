import asyncio
import logging

from juno.exchanges import Exchange

EXCHANGE = 'kraken'
SYMBOL = 'ada-eur'


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        async with exchange.connect_stream_depth(SYMBOL) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
