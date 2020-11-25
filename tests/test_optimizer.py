from decimal import Decimal
from typing import List, Tuple

import pytest

from juno import Candle, Fees, Filters
from juno.components import Prices
from juno.optimizer import Optimizer, OptimizerConfig
from juno.solvers import Rust
from juno.strategies import FourWeekRule
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
    request, loop, long: bool, short: bool
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
            state = await optimizer.initialize(OptimizerConfig(
                exchange='binance',
                start=portfolio_candles[0].time,
                end=portfolio_candles[-1].time + HOUR_MS,
                strategy=FourWeekRule,
                quote=Decimal('1.0'),
                population_size=5,
                max_generations=10,
                seed=1,
                long=long,
                short=short,
            ))
            summary = await optimizer.run(state)
            results.append(summary.portfolio_stats)

    assert results[0].alpha == results[1].alpha
