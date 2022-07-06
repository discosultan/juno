import asyncio
import logging

from asyncstdlib import enumerate as enumerate_async

from juno import Timestamp_
from juno.exchanges import Exchange

# EXCHANGE = 'kraken'
# SYMBOL = 'btc-eur'

EXCHANGE = "binance"
SYMBOL = "eth-btc"


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        # start = Timestamp_.now() - Interval_.MIN
        # end = start + Interval_.MIN + Interval_.SEC_MS
        start = Timestamp_.parse("2020-01-01T23:00:00")
        end = Timestamp_.parse("2020-01-02T01:00:00")
        async for i, val in enumerate_async(
            exchange.stream_historical_trades(symbol=SYMBOL, start=start, end=end)
        ):
            logging.info(val)
            # if i == 2:
            #     break


asyncio.run(main())
