import argparse
import asyncio
import logging
from itertools import product

from juno import storages
from juno.components import Chandler, Trades
from juno.exchanges import Exchange
from juno.time import MIN_MS, floor_timestamp, strftimestamp, strpinterval, strptimestamp, time_ms
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument("symbol", nargs="?", default="eth-btc")
parser.add_argument(
    "intervals",
    nargs="?",
    type=lambda s: map(strpinterval, s.split(",")),
    default=[MIN_MS, 3 * MIN_MS],
)
parser.add_argument("--start", nargs="?", type=strptimestamp, default=None)
parser.add_argument("--end", nargs="?", type=strptimestamp, default=None)
parser.add_argument("--exchange", "-e", default="binance")
parser.add_argument("--storage", default="sqlite")
args = parser.parse_args()

now = time_ms()


async def main() -> None:
    storage = get_module_type(storages, args.storage)()
    exchange = Exchange.from_env(args.exchange)
    trades = Trades(storage=storage, exchanges=[exchange])
    chandler = Chandler(trades=trades, storage=storage, exchanges=[exchange])

    async with exchange, trades, chandler:
        min_interval = min(args.intervals)

        start = (
            (await chandler.get_first_candle(args.exchange, args.symbol, min_interval)).time
            if args.start is None
            else floor_timestamp(args.start, min_interval)
        )
        current = floor_timestamp(now, min_interval)
        end = current if args.end is None else floor_timestamp(args.end, min_interval)

        logging.info(
            f"start {strftimestamp(start)} current {strftimestamp(current)} end "
            f"{strftimestamp(end)}"
        )

        async for candle_meta, candle in chandler.stream_concurrent_candles(
            exchange=args.exchange,
            entries=product([args.symbol], args.intervals),
            start=start,
            end=end,
        ):
            logging.info(f"{candle_meta}: {candle}")


asyncio.run(main())
