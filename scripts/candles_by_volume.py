import asyncio
import logging
from decimal import Decimal

import pandas as pd

from juno import MissedCandlePolicy
from juno.asyncio import list_async
from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.solvers import Python
from juno.storages import SQLite
from juno.strategies import DoubleMA2
from juno.time import strptimestamp
from juno.utils import extract_public


async def main() -> None:
    start = strptimestamp('2020-01-01')
    end = strptimestamp('2020-01-02')
    interval = 1  # Arbitrary.
    binance = init_instance(Binance, from_env())
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    trades = Trades(sqlite, [binance])
    chandler = Chandler(sqlite, [binance], trades=trades)
    solver = Python(informant=informant)
    async with binance, informant:
        candles = await list_async(
            chandler._stream_construct_candles_by_volume(
                'binance', 'eth-btc', Decimal('1000.0'), start, end
            )
        )
        strategy_args = (
            16,
            41,
            Decimal('-0.294'),
            Decimal('0.149'),
            8,
            'sma',
            'sma',
        )
        summary = solver._trade(
            Python.Config(
                fiat_prices={},
                benchmark_g_returns=pd.Series([]),
                candles=candles,
                strategy_type=DoubleMA2,
                strategy_args=strategy_args,
                exchange='binance',
                symbol='eth-btc',
                interval=interval,
                start=start,
                end=end,
                quote=Decimal('1.0'),
                missed_candle_policy=MissedCandlePolicy.IGNORE,
                stop_loss=Decimal('0.1255'),
                trail_stop_loss=True,
                take_profit=Decimal('0.0'),
                long=True,
                short=False,
            )
        )
        logging.info(extract_public(summary))


asyncio.run(main())
