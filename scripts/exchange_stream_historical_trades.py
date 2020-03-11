import asyncio
import logging

from juno import exchanges, time
from juno.asyncio import enumerate_async
from juno.config import from_env, init_instance

# EXCHANGE_TYPE = exchanges.Kraken
# SYMBOL = 'btc-eur'

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        # start = time.time_ms() - time.MIN_MS
        # end = start + time.MIN_MS + time.SEC_MS
        start = time.strptimestamp('2020-01-01T23:00:00')
        end = time.strptimestamp('2020-01-02T01:00:00')
        async for i, val in enumerate_async(
            client.stream_historical_trades(symbol=SYMBOL, start=start, end=end)
        ):
            logging.info(val)
            # if i == 2:
            #     break


asyncio.run(main())
