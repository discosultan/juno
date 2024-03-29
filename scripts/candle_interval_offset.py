import argparse
import asyncio
import logging

from juno import Interval_, Timestamp_
from juno.components import Chandler, Trades
from juno.exchanges import Exchange
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("exchange", nargs="?", default="binance")
parser.add_argument("symbol", nargs="?", default="eth-btc")
parser.add_argument("interval", nargs="?", type=Interval_.parse, default="1d")
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    storage = SQLite()
    trades = Trades(storage=storage, exchanges=[exchange])
    chandler = Chandler(storage=storage, exchanges=[exchange], trades=trades)

    async with exchange, storage, trades, chandler:
        candle = await chandler.get_first_candle(args.exchange, args.symbol, args.interval)

    offset = candle.time % args.interval
    logging.info(
        f"{args.exchange} {args.symbol} {Interval_.format(args.interval)} candle "
        f"{Timestamp_.format(candle.time)} offset is {offset} ({Interval_.format(offset)})"
    )


asyncio.run(main())
