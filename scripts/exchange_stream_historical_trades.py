import asyncio
import logging

from juno import time
from juno.asyncio import enumerate_async
from juno.exchanges import Exchange

# EXCHANGE = 'kraken'
# SYMBOL = 'btc-eur'

EXCHANGE = 'binance'
SYMBOL = 'eth-btc'


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        # start = time.time_ms() - time.MIN_MS
        # end = start + time.MIN_MS + time.SEC_MS
        start = time.strptimestamp('2020-01-01T23:00:00')
        end = time.strptimestamp('2020-01-02T01:00:00')
        async for i, val in enumerate_async(
            exchange.stream_historical_trades(symbol=SYMBOL, start=start, end=end)
        ):
            logging.info(val)
            # if i == 2:
            #     break


asyncio.run(main())
