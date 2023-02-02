import argparse
import asyncio
import logging
from typing import Optional

from juno import Candle, Interval_, Timestamp_, json
from juno.components import Chandler
from juno.exchanges import Exchange
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--symbol", default="btc-usdt")
parser.add_argument("-i", "--interval", type=Interval_.parse, default=Interval_.HOUR)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        chandler = Chandler(storage=SQLite(), exchanges=[exchange])
        start = (
            await chandler.get_first_candle(
                exchange=args.exchange, symbol=args.symbol, interval=args.interval
            )
        ).time
        end = Timestamp_.floor(Timestamp_.now(), args.interval)
        previous_candle: Optional[Candle] = None
        gaps = []
        async for candle in chandler.stream_candles(
            exchange=args.exchange,
            symbol=args.symbol,
            interval=args.interval,
            start=start,
            end=end,
        ):
            if previous_candle is None:
                previous_candle = candle
                continue

            diff = candle.time - previous_candle.time
            if diff > args.interval:
                gaps.append((previous_candle.time, candle.time))

            previous_candle = candle

    formatted_gaps = json.dumps(
        [f"{Timestamp_.format(s)} - {Timestamp_.format(e)}" for s, e in gaps], indent=4
    )
    logging.info(
        f"All gaps of missing {args.exchange} {args.symbol} {Interval_.format(args.interval)} "
        f"candles:\n{formatted_gaps}"
    )


asyncio.run(main())
