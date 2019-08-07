from decimal import Decimal
from typing import Generic, Type, TypeVar

from .di import DI

T = TypeVar('T', float, Decimal)


# Directional Movement Index
class DX(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._di: DI[T] = DI(period, dec=dec)
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: T, low: T, close: T) -> None:
        self._di.update(high, low, close)

        if self._t == self._t1:
            dm_diff = abs(self._di.plus_value - self._di.minus_value)
            dm_sum = self._di.plus_value + self._di.minus_value
            self.value = dm_diff / dm_sum * 100

        self._t = min(self._t + 1, self._t1)
