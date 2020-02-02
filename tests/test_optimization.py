from juno import Candle
from juno.optimization import Optimizer, Rust
from juno.time import HOUR_MS
from juno.utils import load_json_file

from . import fakes


async def rust_solver():
    async with Rust() as rust:
        yield rust


async def test_optimizer_same_result_with_predefined_seed(rust_solver):
    path = f'./data/backtest_scenario1_candles.json'
    # TODO: Load from JSON based on type.
    candles=list(map(lambda c: Candle(**c, closed=True), load_json_file(__file__, path)))
    chandler = fakes.Chandler(candles=candles)
    informant = fakes.Informant(
        candle_intervals=[HOUR_MS],
        symbols=['eth-btc']
    )

    results = []
    for _ in range(0, 2):
        optimizer = Optimizer(
            rust_solver,
            chandler,
            informant,
            'exchange',
            candles[0].time,
            candles[-1].time + HOUR_MS,
            
        )