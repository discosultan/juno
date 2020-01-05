from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Type, get_type_hints

from juno import Candle, Fees, Filters, Interval, Timestamp
from juno.strategies import Strategy
from juno.trading import MissedCandlePolicy, PortfolioStatistics, Statistics, TradingSummary


class Solver(ABC):
    @abstractmethod
    def solve(
        self,
        base_fiat_candles: List[Candle],
        portfolio_candles: List[Candle],
        benchmark_stats: Statistics,
        strategy_type: Type[Strategy],
        quote: Decimal,
        candles: List[Candle],
        fees: Fees,
        filters: Filters,
        symbol: str,
        interval: Interval,
        missed_candle_policy: MissedCandlePolicy,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        pass


class SolverResult(NamedTuple):
    profit: float = 0.0
    mean_drawdown: float = 0.0
    max_drawdown: float = 0.0
    mean_position_profit: float = 0.0
    mean_position_duration: Timestamp = 0
    num_positions_in_profit: int = 0
    num_positions_in_loss: int = 0
    alpha: float = 0.0

    @staticmethod
    def meta(include_disabled: bool = False) -> Dict[str, float]:
        # We try to maximize properties with positive weight, minimize properties with negative
        # weight.
        META = {
            'profit': 1.0,
            'mean_drawdown': -1.0,
            'max_drawdown': -1.0,
            'mean_position_profit': 1.0,
            'mean_position_duration': -1.0,
            'num_positions_in_profit': 1.0,
            'num_positions_in_loss': -1.0,
            'alpha': 1.0,
        }
        if include_disabled:
            return META
        return {k: v for k, v in META.items() if k in _SOLVER_RESULT_KEYS}

    @staticmethod
    def from_trading_summary(
        summary: TradingSummary, stats: PortfolioStatistics
    ) -> SolverResult:
        return SolverResult(
            *map(_decimal_to_float, (getattr(summary, k, None) or getattr(stats, k)
                 for k in _SOLVER_RESULT_KEYS)),
        )

    @staticmethod
    def from_object(obj: Any) -> SolverResult:
        return SolverResult(*(getattr(obj, k) for k in _SOLVER_RESULT_KEYS))


_SOLVER_RESULT_KEYS = list(get_type_hints(SolverResult).keys())


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val
