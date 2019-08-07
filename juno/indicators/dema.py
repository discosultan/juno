from decimal import Decimal
from typing import Generic, Type, TypeVar

from .ema import Ema

T = TypeVar('T', float, Decimal)


# Double Exponential Moving Average
class Dema(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._ema1: Ema[T] = Ema(period, dec=dec)
        self._ema2: Ema[T] = Ema(period, dec=dec)
        self._t = 0
        self._t1 = period - 1
        self._t2 = self._t1 * 2
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, price: T) -> None:
        self._ema1.update(price)

        if self._t <= self._t1:
            self._ema2.update(price)

        if self._t >= self._t1:
            self._ema2.update(self._ema1.value)
            if self._t == self._t2:
                self.value = self._ema1.value * self._dec(2) - self._ema2.value

        self._t = min(self._t + 1, self._t2)
