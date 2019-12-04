from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Tuple, Type, get_type_hints

from juno import Candle, Fees, Filters
from juno.strategies import Strategy
from juno.trading import TradingSummary


class Solver(ABC):
    @abstractmethod
    def solve(
        self,
        strategy_type: Type[Strategy],
        exchange: str,
        quote: Decimal,
        candles: List[Candle],
        fees: Fees,
        filters: Filters,
        symbol: str,
        interval: int,
        missed_candle_policy: int,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        pass


class SolverResult(NamedTuple):
    profit: float = 0.0
    mean_drawdown: float = 0.0
    max_drawdown: float = 0.0
    mean_position_profit: float = 0.0
    mean_position_duration: int = 0
    num_positions_in_profit: int = 0
    num_positions_in_loss: int = 0

    @staticmethod
    def meta(include_disabled: bool = False) -> Dict[str, Tuple[str, float]]:
        # We try to maximize properties with positive weight, minimize properties with negative
        # weight.
        META = {
            'profit': ('f64', 1.0),
            'mean_drawdown': ('f64', -1.0),
            'max_drawdown': ('f64', -1.0),
            'mean_position_profit': ('f64', 1.0),
            'mean_position_duration': ('u64', -1.0),
            'num_positions_in_profit': ('u32', 1.0),
            'num_positions_in_loss': ('u32', -1.0),
        }
        if include_disabled:
            return META
        return {k: v for k, v in META.items() if k in _SOLVER_RESULT_KEYS}

    @staticmethod
    def from_trading_summary(summary: TradingSummary) -> SolverResult:
        return SolverResult(
            *map(_decimal_to_float, (getattr(summary, k) for k in _SOLVER_RESULT_KEYS))
        )

    @staticmethod
    def from_object(obj: Any) -> SolverResult:
        return SolverResult(*(getattr(obj, k) for k in _SOLVER_RESULT_KEYS))


_SOLVER_RESULT_KEYS = list(get_type_hints(SolverResult).keys())


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val
