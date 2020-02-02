from decimal import Decimal
from typing import List, Tuple

import pytest

from juno import Candle, Fees, Filters
from juno.optimization import Optimizer, Rust
from juno.strategies import MAMACX
from juno.time import DAY_MS, HOUR_MS
from juno.typing import load_by_typing
from juno.utils import load_json_file

from . import fakes


@pytest.fixture
async def rust_solver(loop):
    async with Rust() as rust:
        yield rust


async def test_optimizer_same_result_with_predefined_seed(rust_solver):
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
        ('exchange', 'eth-btc', HOUR_MS): portfolio_candles,
        ('exchange', 'eth-btc', DAY_MS): statistics_candles,
        ('coinbase', 'btc-eur', DAY_MS): statistics_fiat_candles,
    })
    informant = fakes.Informant(
        candle_intervals=[HOUR_MS],
        symbols=['eth-btc'],
        fees=fees,
        filters=filters
    )

    results = []
    for _ in range(0, 2):
        optimizer = Optimizer(
            solver=rust_solver,
            chandler=chandler,
            informant=informant,
            exchange='exchange',
            start=portfolio_candles[0].time,
            end=portfolio_candles[-1].time + HOUR_MS,
            strategy_type=MAMACX,
            quote=Decimal('1.0'),
            population_size=50,
            max_generations=100,
            seed=1
        )
        await optimizer.run()
        results.append(optimizer.result.result)

    assert results[0].alpha == results[1].alpha
