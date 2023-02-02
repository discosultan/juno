import argparse
import asyncio
import logging

from asyncstdlib import list as list_async

from juno import Interval_, Timestamp_, json, storages
from juno.components import Chandler, Trades
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--symbol", default="btc-usdt")
parser.add_argument("-i", "--interval", type=Interval_.parse, default=Interval_.HOUR)
parser.add_argument("--start", type=Timestamp_.parse)
parser.add_argument("--end", type=Timestamp_.parse)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        storage = storages.SQLite()
        trades = Trades(storage=storage, exchanges=[exchange])
        chandler = Chandler(storage=storage, exchanges=[exchange], trades=trades)
        candles = await list_async(
            chandler._stream_construct_candles(
                exchange=args.exchange,
                symbol=args.symbol,
                interval=args.interval,
                start=args.start,
                end=args.end,
            )
        )

    formatted_candles = json.dumps([f"{c}" for c in candles], indent=4)
    logging.info(
        f"All constructed {args.exchange} {args.symbol} {Interval_.format(args.interval)} candles "
        f"from trades:\n{formatted_candles}"
    )


asyncio.run(main())
