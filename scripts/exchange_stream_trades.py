import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Kraken
SYMBOL = 'btc-eur'


async def main():
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        async with client.connect_stream_trades(symbol=SYMBOL) as stream:
            i = 0
            async for val in stream:
                logging.info(val)
                i += 1
                if i == 2:
                    break


asyncio.run(main())
