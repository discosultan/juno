from decimal import Decimal
from typing import Generic, Type, TypeVar

from .sma import Sma

T = TypeVar('T', float, Decimal)


# Smoothed Moving Average
class Smma(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._sma: Sma[T] = Sma(period, dec=dec)
        self._weight = period
        self._t = 0
        self._t1 = period - 1
        self._t2 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: T) -> None:
        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t == self._t2:
            self.value = (self.value * (self._weight - 1) + price) / self._weight

        self._t = min(self._t + 1, self._t2)
