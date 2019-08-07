from __future__ import annotations

from decimal import Decimal
from typing import Generic, Type, TypeVar

from juno.utils import CircularBuffer

from .rsi import Rsi

T = TypeVar('T', float, Decimal)


# Stochastic Relative Strength Index
class StochRsi(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        if period < 2:
            raise ValueError(f'Invalid period ({period})')

        self.value: T = dec(0)
        self._rsi: Rsi[T] = Rsi(period, dec=dec)
        self._min: T = dec(0)
        self._max: T = dec(0)
        self._rsi_values: CircularBuffer[T] = CircularBuffer(period, dec(0))
        self._t = 0
        self._t1 = period
        self._t2 = period * 2 - 1
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, price: T) -> None:
        self._rsi.update(price)

        if self._t >= self._t1:
            self._rsi_values.push(self._rsi.value)

        if self._t == self._t2:
            self._min = min(self._rsi_values)
            self._max = max(self._rsi_values)
            diff = self._max - self._min
            if diff == self._dec(0):
                self.value = self._dec(0)
            else:
                self.value = (self._rsi.value - self._min) / diff

        self._t = min(self._t + 1, self._t2)
