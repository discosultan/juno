import asyncio
import logging
from decimal import Decimal

import pandas as pd

from juno.asyncio import list_async
from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.optimization.python import Python, _trade
from juno.storages import SQLite
from juno.strategies import MAMACX
from juno.time import strptimestamp
from juno.trading import MissedCandlePolicy
from juno.utils import tonamedtuple


async def main() -> None:
    start = strptimestamp('2020-01-01')
    end = strptimestamp('2020-01-02')
    interval = 1  # Arbitrary.
    binance = init_instance(Binance, from_env())
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    trades = Trades(sqlite, [binance])
    chandler = Chandler(sqlite, [binance], informant=informant, trades=trades)
    async with binance, informant:
        candles = await list_async(
            chandler._stream_construct_candles_by_volume(
                'binance', 'eth-btc', Decimal('1000.0'), start, end
            )
        )
        fees, filters = informant.get_fees_filters('binance', 'eth-btc')
        strategy_args = (
            16,
            41,
            Decimal('-0.294'),
            Decimal('0.149'),
            8,
            'sma',
            'sma',
        )
        summary = _trade(
            Python.Config(
                fiat_daily_prices={},
                benchmark_g_returns=pd.Series([]),
                candles=candles,
                fees=fees,
                filters=filters,
                strategy_type=MAMACX,
                strategy_args=strategy_args,
                symbol='eth-btc',
                interval=interval,
                start=start,
                end=end,
                quote=Decimal('1.0'),
                missed_candle_policy=MissedCandlePolicy.IGNORE,
                trailing_stop=Decimal('0.1255'),
                long=True,
                short=False,
            )
        )
        logging.info(tonamedtuple(summary))


asyncio.run(main())
