from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable, NamedTuple, Type

from juno.strategies import Strategy
from juno.trading import TradingSummary


class Solver(ABC):
    @abstractmethod
    async def get(
        self,
        strategy_type: Type[Strategy],
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int,
        quote: Decimal,
    ) -> Callable[..., Any]:
        pass


class SolverResult(NamedTuple):
    profit: float
    mean_drawdown: float
    max_drawdown: float
    mean_position_profit: float
    mean_position_duration: int
    num_positions_in_profit: int
    num_positions_in_loss: int

    @staticmethod
    def from_trading_summary(summary: TradingSummary) -> SolverResult:
        return SolverResult(
            float(summary.profit),
            float(summary.mean_drawdown),
            float(summary.max_drawdown),
            float(summary.mean_position_profit),
            summary.mean_position_duration,
            summary.num_positions_in_profit,
            summary.num_positions_in_loss,
        )
