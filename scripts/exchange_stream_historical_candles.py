import argparse
import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance
from juno.time import strpinterval, strptimestamp

EXCHANGE_TYPE = exchanges.Binance

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?')
parser.add_argument('interval', nargs='?', type=strpinterval)
parser.add_argument('start', nargs='?', type=strptimestamp)
parser.add_argument('end', nargs='?', type=strptimestamp)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        async for candle in client.stream_historical_candles(
            args.symbol, args.interval, args.start, args.end
        ):
            logging.info(candle)


asyncio.run(main())
