import argparse
import asyncio
import logging
from itertools import product

from juno import Interval, Interval_, Symbol, Timestamp_
from juno.components import Chandler, Trades
from juno.exchanges import Exchange
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("symbols", nargs="?", type=lambda s: s.split(","), default=["eth-btc"])
parser.add_argument(
    "intervals",
    nargs="?",
    type=lambda s: map(Interval_.parse, s.split(",")),
    default=[Interval_.HOUR],
)
parser.add_argument("--exchange", "-e", default="binance")
args = parser.parse_args()


async def main() -> None:
    sqlite = SQLite()
    exchange = Exchange.from_env(args.exchange)
    trades = Trades(sqlite, [exchange])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[exchange])
    async with exchange, trades, chandler:
        await asyncio.gather(
            *(log_first_last(chandler, s, i) for s, i in product(args.symbols, args.intervals))
        )


async def log_first_last(chandler: Chandler, symbol: Symbol, interval: Interval) -> None:
    first_candle, last_candle = await asyncio.gather(
        chandler.get_first_candle(args.exchange, symbol, interval),
        chandler.get_last_candle(args.exchange, symbol, interval),
    )
    logging.info(
        f"got the following {symbol} {Interval_.format(interval)} candles at "
        f"{Timestamp_.format(Timestamp_.now())}:"
    )
    logging.info(f"    first - {Timestamp_.format(first_candle.time)} ({first_candle.time})")
    logging.info(f"    last  - {Timestamp_.format(last_candle.time)} ({last_candle.time})")


asyncio.run(main())
