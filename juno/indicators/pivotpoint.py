from decimal import Decimal
from typing import Generic, Type, TypeVar

T = TypeVar('T', float, Decimal)


class PivotPoint(Generic[T]):
    def __init__(self, dec: Type[T] = Decimal) -> None:  # type: ignore
        pass

    @property
    def req_history(self) -> int:
        return 0

    def update(self, high: T, low: T, close: T) -> None:
        pass
        # diff = high - low
        # self.value = (high + low + close) / 3
        # self.support1 = 2 * self.value - high
        # self.support2 = self.value - diff
        # self.resistance1 = 2 * self.value - low
        # self.resistance2 = self.value + diff
