import argparse
import asyncio
import logging

from juno import Interval_, Timestamp_
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("symbol", nargs="?")
parser.add_argument("interval", nargs="?", type=Interval_.parse)
parser.add_argument("start", nargs="?", type=Timestamp_.parse)
parser.add_argument("end", nargs="?", type=Timestamp_.parse)
parser.add_argument("-e", "--exchange", default="binance")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        async for candle in exchange.stream_historical_candles(
            args.symbol, args.interval, args.start, args.end
        ):
            logging.info(candle)


asyncio.run(main())
