from __future__ import annotations

from decimal import Decimal

from .sma import Sma


# Exponential Moving Average
class Ema2:

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value = Decimal(0)
        self._sma = Sma(period)
        self._a = Decimal(2) / (period + 1)  # Smoothing factor.
        self._t = 0
        self._t1 = period - 1
        self._t2 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t == self._t2:
            self.value = (price - self.value) * self._a + self.value

        self._t = min(self._t + 1, self._t2)

    @staticmethod
    def with_smoothing(a: Decimal) -> Ema2:  # noqa
        dummy_period = 1
        ema = Ema2(dummy_period)
        ema._a = a
        return ema
