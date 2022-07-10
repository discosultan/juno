import argparse
import asyncio
import logging
from itertools import product

from asyncstdlib import enumerate as enumerate_async

from juno import Interval, Interval_, Symbol, Timestamp_, storages
from juno.components import Chandler, Trades
from juno.exchanges import Exchange
from juno.inspect import get_module_type
from juno.path import save_json_file

DUMP_AS_JSON = False
LOG_CANDLES = False

parser = argparse.ArgumentParser()
parser.add_argument("symbols", nargs="?", type=lambda s: s.split(","), default=["eth-btc"])
parser.add_argument(
    "intervals",
    nargs="?",
    type=lambda s: map(Interval_.parse, s.split(",")),
    default=[Interval_.MIN],
)
parser.add_argument("start", nargs="?", type=Timestamp_.parse, default=None)
parser.add_argument("end", nargs="?", type=Timestamp_.parse, default=None)
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
        await asyncio.gather(
            *(stream_candles(chandler, s, i) for s, i in product(args.symbols, args.intervals))
        )


async def stream_candles(chandler: Chandler, symbol: Symbol, interval: Interval) -> None:
    start = (
        (await chandler.get_first_candle(args.exchange, symbol, interval)).time
        if args.start is None
        else Timestamp_.floor(args.start, interval)
    )
    current = Timestamp_.floor(now, interval)
    end = current if args.end is None else Timestamp_.floor(args.end, interval)

    logging.info(
        f"start {Timestamp_.format(start)} current {Timestamp_.format(current)} end "
        f"{Timestamp_.format(end)}"
    )

    candles = []
    async for i, candle in enumerate_async(
        chandler.stream_candles(
            args.exchange,
            symbol,
            interval,
            start,
            end,
        )
    ):
        if DUMP_AS_JSON:
            candles.append(candle)

        if LOG_CANDLES:
            historical_or_future = "future" if candle.time >= current else "historical"
            logging.info(f"{historical_or_future} candle {i}: {candle}")

    if DUMP_AS_JSON:
        save_json_file(candles, f"{args.exchange}_{symbol}_{interval}_candles.json", indent=4)


asyncio.run(main())
