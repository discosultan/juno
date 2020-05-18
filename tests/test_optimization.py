import math
from decimal import Decimal
from typing import List, Tuple

import pytest

from juno import Candle, Fees, Filters, MissedCandlePolicy
from juno.components import Prices
from juno.optimization import Optimizer, Rust
from juno.statistics import analyse_benchmark
from juno.strategies import MAMACX
from juno.time import DAY_MS, HOUR_MS
from juno.traders import Basic
from juno.typing import raw_to_type
from juno.utils import load_json_file

from . import fakes


@pytest.mark.parametrize('long,short', [
    (True, False),
    # (False, True),
    (True, True),
    # (False, False),
])
async def test_optimizer_same_result_with_predefined_seed(
    request, long: bool, short: bool
) -> None:
    portfolio_candles = raw_to_type(
        load_json_file(__file__, './data/binance_eth-btc_3600000_candles.json'),
        List[Candle]
    )
    statistics_candles = raw_to_type(
        load_json_file(__file__, './data/binance_eth-btc_86400000_candles.json'),
        List[Candle]
    )
    # TODO: Use binance usdt candles instead.
    statistics_fiat_candles = raw_to_type(
        load_json_file(__file__, './data/coinbase_btc-eur_86400000_candles.json'),
        List[Candle]
    )
    fees, filters = raw_to_type(
        load_json_file(__file__, './data/binance_eth-btc_fees_filters.json'),
        Tuple[Fees, Filters]
    )
    chandler = fakes.Chandler(candles={
        ('binance', 'eth-btc', HOUR_MS): portfolio_candles,
        ('binance', 'eth-btc', DAY_MS): statistics_candles,
        ('binance', 'btc-usdt', DAY_MS): statistics_fiat_candles,
    })
    prices = Prices(chandler=chandler)
    informant = fakes.Informant(
        candle_intervals=[HOUR_MS],
        symbols=['eth-btc'],
        fees=fees,
        filters=filters
    )
    rust_solver = Rust(informant=informant)
    trader = Basic(chandler=chandler, informant=informant)
    optimizer = Optimizer(
        solver=rust_solver, chandler=chandler, informant=informant, prices=prices, trader=trader,
    )

    results = []

    async with rust_solver:
        for _ in range(0, 2):
            summary = await optimizer.run(
                exchange='binance',
                start=portfolio_candles[0].time,
                end=portfolio_candles[-1].time + HOUR_MS,
                strategy='mamacx',
                quote=Decimal('1.0'),
                population_size=5,
                max_generations=10,
                seed=1,
                long=long,
                short=short,
            )
            results.append(summary.best[0].portfolio_stats)

    assert results[0].alpha == results[1].alpha


async def test_rust_solver_works_with_default_fees_filters() -> None:
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
    fiat_daily_candles = {
        'btc': [c.close for c in statistics_fiat_candles],
        'eth': [c1.close * c2.close for c1, c2 in zip(statistics_candles, statistics_fiat_candles)]
    }
    benchmark_stats = analyse_benchmark(fiat_daily_candles['btc'])
    strategy_args = (11, 21, Decimal('-0.229'), Decimal('0.1'), 4, 'ema', 'ema')

    async with Rust(informant=fakes.Informant()) as rust_solver:
        result = rust_solver.solve(
            Rust.Config(
                fiat_daily_prices=fiat_daily_candles,
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
                trailing_stop=Decimal('0.0'),
                long=True,
                short=False,
                strategy_args=strategy_args,
            )
        )

    assert not math.isnan(result.alpha)
