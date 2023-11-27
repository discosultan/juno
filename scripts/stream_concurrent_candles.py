import argparse
import asyncio
import logging
from itertools import product

from juno import Interval_, Timestamp_, storages
from juno.components import Chandler, Trades
from juno.exchanges import Exchange
from juno.inspect import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument("symbol", nargs="?", default="eth-btc")
parser.add_argument(
    "intervals",
    nargs="?",
    type=lambda s: list(map(Interval_.parse, s.split(","))),
    default=[Interval_.MIN, 3 * Interval_.MIN],
)
parser.add_argument("--start", nargs="?", type=Timestamp_.parse, default=None)
parser.add_argument("--end", nargs="?", type=Timestamp_.parse, default=None)
parser.add_argument("--exchange", "-e", default="binance")
parser.add_argument("--storage", default="sqlite")
args = parser.parse_args()

now = Timestamp_.now()


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
            else Timestamp_.floor(args.start, min_interval)
        )
        current = Timestamp_.floor(now, min_interval)
        end = current if args.end is None else Timestamp_.floor(args.end, min_interval)

        logging.info(
            f"start {Timestamp_.format(start)} current {Timestamp_.format(current)} end "
            f"{Timestamp_.format(end)}"
        )
        logging.info(f"symbol {args.symbol} intervals {args.intervals}")

        async for candle_meta, candle in chandler.stream_concurrent_candles(
            exchange=args.exchange,
            entries=list(product([args.symbol], args.intervals, ["regular"])),
            start=start,
            end=end,
        ):
            logging.info(f"{candle_meta}: {candle}")


asyncio.run(main())
