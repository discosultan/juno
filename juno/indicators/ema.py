from __future__ import annotations

from decimal import Decimal

from .sma import Sma


# Exponential Moving Average
class Ema:
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value = Decimal('0.0')
        self._a = Decimal('2.0') / (period + 1)  # Smoothing factor.
        self._t = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, price: Decimal) -> None:
        if self._t == 0:
            self.value = price
            self._t = 1
        else:
            self.value = (price - self.value) * self._a + self.value

    @staticmethod
    def with_smoothing(a: Decimal) -> Ema:
        dummy_period = 1
        ema = Ema(dummy_period)
        ema._a = a
        return ema


class Ema2(Ema):
    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._sma = Sma(period)
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
