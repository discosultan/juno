from __future__ import annotations

import math
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Type, get_type_hints

import pandas as pd

from juno import Candle, Interval, MissedCandlePolicy, Timestamp
from juno.statistics import Statistics
from juno.strategies import Strategy
from juno.trading import TradingSummary
from juno.utils import AbstractAsyncContextManager, unpack_symbol


class Solver(AbstractAsyncContextManager, ABC):
    class Config(NamedTuple):
        fiat_prices: Dict[str, List[Decimal]]
        benchmark_g_returns: pd.Series
        candles: List[Candle]
        strategy_type: Type[Strategy]
        strategy_args: Tuple[Any, ...]
        exchange: str
        symbol: str
        interval: Interval
        start: Timestamp
        end: Timestamp
        quote: Decimal
        stop_loss: Decimal
        trail_stop_loss: bool
        take_profit: Decimal
        missed_candle_policy: MissedCandlePolicy
        long: bool
        short: bool

        @property
        def base_asset(self) -> str:
            return unpack_symbol(self.symbol)[0]

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

        def new_strategy(self) -> Strategy:
            return self.strategy_type(*self.strategy_args)

    @abstractmethod
    def solve(self, config: Config) -> SolverResult:
        pass


_META = {
    'alpha': +1.0,
    'sharpe_ratio': +1.0,
    'sortino_ratio': +1.0,
    'profit': +1.0,
    'mean_drawdown': -1.0,
    'max_drawdown': -1.0,
    'mean_position_profit': +1.0,
    'mean_position_duration': -1.0,
    'num_positions': +1.0,
    'num_positions_in_profit': +1.0,
    'num_positions_in_loss': -1.0,
}


def _map_nan(key: str, value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        weight = _META[key]
        if weight == 0:
            return 0.0
        if weight < 0:
            return float('inf')
        if weight > 0:
            return float('-inf')
    return value


class SolverResult(NamedTuple):
    # alpha: float = 0.0
    sharpe_ratio: float = 0.0
    # sortino_ratio: float = 0.0
    # profit: float = 0.0
    # mean_drawdown: float = 0.0
    # max_drawdown: float = 0.0
    # mean_position_profit: float = 0.0
    # mean_position_duration: Interval = 0
    # num_positions: int = 0
    # num_positions_in_profit: int = 0
    # num_positions_in_loss: int = 0

    @staticmethod
    def meta() -> Dict[str, float]:
        # NB! There's an issue with optimizing more than 3 objectives:
        # https://stackoverflow.com/q/44929118/1466456
        # We try to maximize properties with positive weight, minimize properties with negative
        # weight.
        return {k: _META[k] for k in _SOLVER_RESULT_KEYS}
        # if include_disabled:
        #     return META
        # return {k: v for k, v in META.items() if k in _SOLVER_RESULT_KEYS}

    @staticmethod
    def _new(*iterable: Any) -> SolverResult:
        # We map nan to infinity values because otherwise they will mess up fitness comparisons.
        # See: https://github.com/DEAP/deap/issues/440
        return SolverResult(
            *(_map_nan(k, v) for k, v in zip(_SOLVER_RESULT_KEYS, iterable))
        )

    @staticmethod
    def from_trading_summary(
        summary: TradingSummary, stats: Statistics
    ) -> SolverResult:
        return SolverResult._new(*map(
            _decimal_to_float,
            (_coalesce(
                getattr(summary, k, None),
                lambda: getattr(stats, k)
            ) for k in _SOLVER_RESULT_KEYS)
        ))

    @staticmethod
    def from_object(obj: Any) -> SolverResult:
        return SolverResult._new(*(getattr(obj, k) for k in _SOLVER_RESULT_KEYS))


_SOLVER_RESULT_KEYS = list(get_type_hints(SolverResult).keys())


def _coalesce(val: Optional[Any], default: Callable[[], Any]) -> Any:
    return val if val is not None else default()


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val
