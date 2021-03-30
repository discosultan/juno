import asyncio
import logging
import math

import numpy as np
import pandas as pd
from more_itertools import take

from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.math import floor_multiple_offset
from juno.storages import SQLite
from juno.time import MONTH_MS, YEAR_MS, strfinterval, time_ms


async def find_volatility_for_symbol(chandler, exchange, symbol, interval, start, end):
    candles = await chandler.list_candles(exchange, symbol, interval, start, end)
    df = pd.DataFrame([float(c.close) for c in candles], columns=['price'])
    # Find returns.
    df['pct_chg'] = df['price'].pct_change()
    # Find log returns.
    df['log_ret'] = np.log(1 + df['pct_chg'])
    # df['log_ret'] = np.log(df['price']) - np.log(df['price'].shift(1))
    # Find volatility.
    volatility = df['log_ret'].std(ddof=0)
    annualized_volatility = volatility * ((YEAR_MS / interval)**0.5)
    return symbol, strfinterval(interval), annualized_volatility


async def main() -> None:
    binance = init_instance(Binance, from_env())
    exchange = 'binance'
    sqlite = SQLite()
    trades = Trades(sqlite, [binance])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[binance])
    informant = Informant(sqlite, [binance])
    async with binance, informant, trades, chandler:
        symbols = informant.list_symbols(exchange)[:10]
        interval_offsets = take(3, informant.map_candle_intervals(exchange).items())
        now = time_ms()
        tasks = []
        for interval, interval_offset in interval_offsets:
            end = floor_multiple_offset(now, interval, interval_offset)
            start = end - MONTH_MS
            for symbol in symbols:
                tasks.append(
                    find_volatility_for_symbol(chandler, exchange, symbol, interval, start, end)
                )
        results = await asyncio.gather(*tasks)

        results = [r for r in results if not math.isnan(r[2])]
        logging.info(results)

        best = max(results, key=lambda v: v[2])  # By volatility.
        logging.info(best)


asyncio.run(main())
