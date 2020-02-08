from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Type, get_type_hints

from juno import Candle, Fees, Filters, Interval, Timestamp
from juno.strategies import Strategy
from juno.trading import MissedCandlePolicy, PortfolioStatistics, Statistics, TradingSummary


class Solver(ABC):
    @abstractmethod
    def solve(
        self,
        fiat_daily_prices: Dict[str, List[Decimal]],
        benchmark_stats: Statistics,
        strategy_type: Type[Strategy],
        start: Timestamp,
        end: Timestamp,
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
    alpha: float = 0.0
    # profit: float = 0.0
    # mean_drawdown: float = 0.0
    # max_drawdown: float = 0.0
    # mean_position_profit: float = 0.0
    # mean_position_duration: Interval = 0
    # num_positions_in_profit: int = 0
    # num_positions_in_loss: int = 0

    @staticmethod
    def meta() -> Dict[str, float]:
        # NB! There's an issue with optimizing more than 3 objectives:
        # https://stackoverflow.com/q/44929118/1466456
        # We try to maximize properties with positive weight, minimize properties with negative
        # weight.
        META = {
            'alpha': 1.0,  # +
            # 'profit': 1.0,  # +
            # 'mean_drawdown': -1.0,  # -
            # 'max_drawdown': -1.0,  # -
            # 'mean_position_profit': 1.0,  # +
            # 'mean_position_duration': -1.0,  # -
            # 'num_positions_in_profit': 1.0,  # +
            # 'num_positions_in_loss': -1.0,  # -
        }
        return {k: META.get(k, 0.00000001) for k in _SOLVER_RESULT_KEYS}
        # if include_disabled:
        #     return META
        # return {k: v for k, v in META.items() if k in _SOLVER_RESULT_KEYS}

    @staticmethod
    def from_trading_summary(
        summary: TradingSummary, stats: PortfolioStatistics
    ) -> SolverResult:
        return SolverResult(*map(
            _decimal_to_float,
            (_coalesce(
                getattr(summary, k, None),
                lambda: getattr(stats, k)
            ) for k in _SOLVER_RESULT_KEYS)
        ))

    @staticmethod
    def from_object(obj: Any) -> SolverResult:
        return SolverResult(*(getattr(obj, k) for k in _SOLVER_RESULT_KEYS))


_SOLVER_RESULT_KEYS = list(get_type_hints(SolverResult).keys())


def _coalesce(val: Optional[Any], default: Callable[[], Any]) -> Any:
    return val if val is not None else default()


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val
