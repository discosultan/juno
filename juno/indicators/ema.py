from __future__ import annotations

from decimal import Decimal
from typing import Generic, Type, TypeVar

from .sma import Sma

T = TypeVar('T', float, Decimal)


# Exponential Moving Average
class Ema(Generic[T]):
    def __init__(self, period: int, v2: bool = False,  # type: ignore
                 dec: Type[T] = Decimal) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value: T = dec(0)
        self._a: T = dec(2) / (period + 1)  # Smoothing factor.
        self._t = 0
        self._v2 = v2

        if v2:
            self._sma: Sma[T] = Sma(period, dec=dec)
            self._t1 = period - 1
            self._t2 = period

    @property
    def req_history(self) -> int:
        return self._t1 if self._v2 else 0

    def update(self, price: T) -> None:
        if self._v2:
            if self._t <= self._t1:
                self._sma.update(price)

            if self._t == self._t1:
                self.value = self._sma.value
            elif self._t == self._t2:
                self.value = (price - self.value) * self._a + self.value

            self._t = min(self._t + 1, self._t2)
        else:
            if self._t == 0:
                self.value = price
                self._t = 1
            else:
                self.value = (price - self.value) * self._a + self.value

    @staticmethod
    def with_smoothing(a: T, v2: bool = False, dec: Type[T] = Decimal) -> Ema[T]:  # type: ignore
        dummy_period = 1
        ema: Ema[T] = Ema(dummy_period, v2, dec)
        ema._a = a
        return ema
