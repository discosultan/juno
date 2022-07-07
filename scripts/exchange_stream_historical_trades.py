import argparse
import asyncio
import logging

from asyncstdlib import enumerate as enumerate_async

from juno import Timestamp_
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--symbol", default="eth-btc")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        # start = Timestamp_.now() - Interval_.MIN
        # end = start + Interval_.MIN + Interval_.SEC_MS
        start = Timestamp_.parse("2020-01-01T23:00:00")
        end = Timestamp_.parse("2020-01-02T01:00:00")
        async for i, val in enumerate_async(
            exchange.stream_historical_trades(symbol=args.symbol, start=start, end=end)
        ):
            logging.info(val)
            # if i == 2:
            #     break


asyncio.run(main())
