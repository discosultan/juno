import math
from decimal import Decimal
from typing import List

import pytest

from juno import Candle, MissedCandlePolicy
from juno.solvers import Python, Rust
from juno.statistics import analyse_benchmark
from juno.strategies import MAMACX
from juno.time import HOUR_MS
from juno.typing import raw_to_type
from juno.utils import load_json_file

from . import fakes


@pytest.mark.parametrize('solver_type', [Python, Rust])
async def test_solver_works_with_default_fees_filters(loop, solver_type) -> None:
    portfolio_candles = raw_to_type(
        load_json_file(__file__, './data/binance_eth-btc_3600000_candles.json'),
        List[Candle]
    )
    statistics_candles = raw_to_type(
        load_json_file(__file__, './data/binance_eth-btc_86400000_candles.json'),
        List[Candle]
    )
    statistics_fiat_candles = raw_to_type(
        load_json_file(__file__, './data/coinbase_btc-eur_86400000_candles.json'),
        List[Candle]
    )
    fiat_prices = {
        'btc': [c.close for c in statistics_fiat_candles],
        'eth': [c1.close * c2.close for c1, c2 in zip(statistics_candles, statistics_fiat_candles)]
    }
    benchmark_stats = analyse_benchmark(fiat_prices['btc'])
    strategy_args = (11, 21, Decimal('-0.229'), Decimal('0.1'), 4, 'ema', 'ema')

    async with solver_type(informant=fakes.Informant()) as solver:
        result = solver.solve(
            solver_type.Config(
                fiat_prices=fiat_prices,
                benchmark_g_returns=benchmark_stats.g_returns,
                strategy_type=MAMACX,
                start=portfolio_candles[0].time,
                end=portfolio_candles[-1].time + HOUR_MS,
                quote=Decimal('1.0'),
                candles=portfolio_candles,
                exchange='exchange',
                symbol='eth-btc',
                interval=HOUR_MS,
                missed_candle_policy=MissedCandlePolicy.IGNORE,
                stop_loss=Decimal('0.0'),
                trail_stop_loss=True,
                take_profit=Decimal('0.0'),
                long=True,
                short=False,
                strategy_args=strategy_args,
            )
        )

    assert not math.isnan(result.alpha)
