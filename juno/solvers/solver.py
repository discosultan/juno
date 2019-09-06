from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable, Type

from juno.strategies import Strategy


class Solver(ABC):
    @abstractmethod
    async def get(
        self, strategy_type: Type[Strategy], exchange: str, symbol: str, interval: int, start: int,
        end: int, quote: Decimal
    ) -> Callable[..., Any]:
        pass
