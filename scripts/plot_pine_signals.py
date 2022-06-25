import asyncio

from juno import Advice
from juno.common import CandleType
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.storages import SQLite
from juno.strategies import ChandelierExit
from juno.time import DAY_MS, strptimestamp


async def main() -> None:
    sqlite = SQLite()
    binance = init_instance(Binance, from_env())
    trades = Trades(sqlite, [binance])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[binance])
    symbol = "eth-btc"
    interval = DAY_MS
    candle_type: CandleType = "regular"
    start = strptimestamp("2022-01-01")
    end = strptimestamp("2022-06-01")
    async with binance, trades, chandler:
        candles = await chandler.list_candles(
            exchange="binance",
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            type_=candle_type,
        )

    strategy = ChandelierExit(
        long_period=22,
        short_period=22,
        atr_period=22,
        atr_multiplier=3,
    )
    time_advices = []
    for candle in candles:
        strategy.update(candle, (symbol, interval, candle_type))
        time_advices.append((candle.time + interval, strategy.advice))

    def adjust_time(time: int) -> int:
        return time - interval

    lines = [
        (
            "// This source code is subject to the terms of the Mozilla Public License 2.0 at "
            "https://mozilla.org/MPL/2.0/"
        ),
        "// © discosultan",
        "",
        "//@version=5",
        'indicator("juno", overlay=true)',
        "",
    ]

    # Longs.
    longs = [(t, a) for t, a in time_advices if a is Advice.LONG]
    lines.append(f"var open_longs = array.new_int({len(longs)})")
    for i, (time, _) in enumerate(longs):
        time = adjust_time(time)
        lines.append(f"array.set(open_longs, {i}, {time})")
    lines.append("open_longs_data = array.includes(open_longs, time)")
    lines.append(
        "plotshape(open_longs_data, style=shape.triangleup, location=location.belowbar, "
        "color=color.green)"
    )

    # Shorts.
    shorts = [(t, a) for t, a in time_advices if a is Advice.SHORT]
    lines.append(f"var open_shorts = array.new_int({len(shorts)})")
    for i, (time, _) in enumerate(shorts):
        time = adjust_time(time)
        lines.append(f"array.set(open_shorts, {i}, {time})")
    lines.append("open_shorts_data = array.includes(open_shorts, time)")
    lines.append(
        "plotshape(open_shorts_data, style=shape.triangledown, location=location.abovebar, "
        "color=color.red)"
    )

    with open("script.pine", "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


asyncio.run(main())
