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
from juno.time import HOUR_MS, MONTH_MS, time_ms

exchange = 'binance'
symbol = 'eth-btc'
interval = HOUR_MS


np.random.seed(0)
df = pd.DataFrame(100 + np.random.randn(100).cumsum(), columns=['price'])
df['pct_change'] = df.price.pct_change()
df['log_ret'] = np.log(df.price) - np.log(df.price.shift(1))
print(df)


# print(100 + np.random.randn(100).cumsum())
# exit()


async def main():
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    async with binance, informant:
        start = floor_multiple(time_ms(), interval) - 4 * MONTH_MS
        end = start + 4 * MONTH_MS
        candles = await list_async(
            informant.stream_candles(exchange, symbol, interval, start, end)
        )
        df = pd.DataFrame([float(c.close) for c in candles], columns=['price'])
        # Find returns.
        df['pct_chg'] = df['price'].pct_change()
        # Find log returns.
        df['log_ret'] = np.log(1 + df['pct_chg'])
        # df['log_ret'] = np.log(df['price']) - np.log(df['price'].shift(1))
        # Find annualized std.
        # `ddof=1` since first value is `NaN`.
        window = len(candles)
        print(window)
        vol = df['log_ret'].rolling(window=2).std(ddof=0) * (365**0.5)
        print(vol)

logging.basicConfig(level='WARNING')
asyncio.run(main())
