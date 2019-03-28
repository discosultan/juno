from __future__ import annotations

from decimal import Decimal

from juno.utils import CircularBuffer

from .rsi import Rsi


# Stochastic Relative Strength Index
class StochRsi:

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f'invalid period ({period})')

        self.value = Decimal(0)
        self._rsi = Rsi(period)
        self._min = Decimal(0)
        self._max = Decimal(0)
        self._rsi_values = CircularBuffer(period, Decimal(0))
        self._t = 0
        self._t1 = period
        self._t2 = period * 2 - 1

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, price: Decimal) -> None:
        self._rsi.update(price)

        if self._t >= self._t1:
            self._rsi_values.push(self._rsi.value)

        if self._t == self._t2:
            self._min = min(self._rsi_values)
            self._max = max(self._rsi_values)
            diff = self._max - self._min
            if diff == Decimal(0):
                self.value = Decimal(0)
            else:
                self.value = (self._rsi.value - self._min) / diff

        self._t = min(self._t + 1, self._t2)
