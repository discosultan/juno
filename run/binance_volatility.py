import asyncio
import logging
import os

import numpy as np
import pandas as pd

from juno.asyncio import list_async
from juno.components import Informant
from juno.exchanges import Binance
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import DAY_MS, MONTH_MS, YEAR_MS, time_ms

exchange = 'binance'
interval = DAY_MS
end = floor_multiple(time_ms(), interval)
start = end - MONTH_MS


async def find_volatility_for_symbol(informant, exchange, symbol, interval, start, end):
    candles = await list_async(informant.stream_candles(exchange, symbol, interval, start, end))
    df = pd.DataFrame([float(c.close) for c in candles], columns=['price'])
    # Find returns.
    df['pct_chg'] = df['price'].pct_change()
    # Find log returns.
    df['log_ret'] = np.log(1 + df['pct_chg'])
    # df['log_ret'] = np.log(df['price']) - np.log(df['price'].shift(1))
    # Find volatility.
    volatility = df['log_ret'].std(ddof=0)
    annualized_volatility = volatility * ((YEAR_MS / interval)**0.5)
    return symbol, annualized_volatility


async def main():
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    async with binance, informant:
        symbols = informant.list_symbols(exchange)[:10]
        tasks = []
        for symbol in symbols:
            tasks.append(
                find_volatility_for_symbol(informant, exchange, symbol, interval, start, end)
            )
        results = await asyncio.gather(*tasks)

        def by_volatility(value):
            return value[1]

        best = max(results, key=by_volatility)
        print(results)
        print(best)


logging.basicConfig(level='WARNING')
asyncio.run(main())
