import math
from decimal import Decimal
from typing import List, Tuple

import pytest

from juno import Candle, Fees, Filters
from juno.components import Prices
from juno.optimization import Optimizer, Rust
from juno.strategies import MAMACX
from juno.time import DAY_MS, HOUR_MS
from juno.trading import MissedCandlePolicy, Trader, get_benchmark_statistics
from juno.typing import load_by_typing
from juno.utils import load_json_file

from . import fakes


@pytest.fixture
async def rust_solver(loop):
    async with Rust() as rust:
        yield rust


async def test_optimizer_same_result_with_predefined_seed(request, rust_solver) -> None:
    portfolio_candles = load_by_typing(
        load_json_file(__file__, './data/binance_eth-btc_3600000_candles.json'),
        List[Candle]
    )
    statistics_candles = load_by_typing(
        load_json_file(__file__, './data/binance_eth-btc_86400000_candles.json'),
        List[Candle]
    )
    statistics_fiat_candles = load_by_typing(
        load_json_file(__file__, './data/coinbase_btc-eur_86400000_candles.json'),
        List[Candle]
    )
    fees, filters = load_by_typing(
        load_json_file(__file__, './data/binance_eth-btc_fees_filters.json'),
        Tuple[Fees, Filters]
    )
    chandler = fakes.Chandler(candles={
        ('binance', 'eth-btc', HOUR_MS): portfolio_candles,
        ('binance', 'eth-btc', DAY_MS): statistics_candles,
        ('coinbase', 'btc-eur', DAY_MS): statistics_fiat_candles,
    })
    prices = Prices(chandler=chandler)
    informant = fakes.Informant(
        candle_intervals=[HOUR_MS],
        symbols=['eth-btc'],
        fees=fees,
        filters=filters
    )
    trader = Trader(chandler=chandler, informant=informant)

    results = []
    for _ in range(0, 2):
        optimizer = Optimizer(
            solver=rust_solver,
            chandler=chandler,
            informant=informant,
            prices=prices,
            trader=trader,
            exchange='binance',
            start=portfolio_candles[0].time,
            end=portfolio_candles[-1].time + HOUR_MS,
            strategy_type=MAMACX,
            quote=Decimal('1.0'),
            population_size=5,
            max_generations=10,
            seed=1
        )
        await optimizer.run()
        results.append(optimizer.result.result)

    assert results[0].alpha == results[1].alpha


async def test_rust_solver_works_with_default_fees_filters(rust_solver: Rust) -> None:
    portfolio_candles = load_by_typing(
        load_json_file(__file__, './data/binance_eth-btc_3600000_candles.json'),
        List[Candle]
    )
    statistics_candles = load_by_typing(
        load_json_file(__file__, './data/binance_eth-btc_86400000_candles.json'),
        List[Candle]
    )
    statistics_fiat_candles = load_by_typing(
        load_json_file(__file__, './data/coinbase_btc-eur_86400000_candles.json'),
        List[Candle]
    )
    fiat_daily_candles = {
        'btc': [c.close for c in statistics_fiat_candles],
        'eth': [c1.close * c2.close for c1, c2 in zip(statistics_candles, statistics_fiat_candles)]
    }
    benchmark_stats = get_benchmark_statistics(fiat_daily_candles['btc'])
    strategy_args = (11, 21, Decimal('-0.229'), Decimal('0.1'), 4, 0, 0)

    result = rust_solver.solve(
        fiat_daily_candles,
        benchmark_stats,
        MAMACX,
        portfolio_candles[0].time,
        portfolio_candles[-1].time + HOUR_MS,
        Decimal('1.0'),
        portfolio_candles,
        Fees(),
        Filters(),
        'eth-btc',
        HOUR_MS,
        MissedCandlePolicy.IGNORE,
        Decimal('0.0'),
        *strategy_args
    )

    assert not math.isnan(result.alpha)
