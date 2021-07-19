from __future__ import annotations

from decimal import Decimal

from .sma import Sma


class Ema2:
    value: Decimal = Decimal("0.0")

    _sma: Sma
    _a: Decimal
    _t: int = 0
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

        self._sma = Sma(period)

        self._a = Decimal("2.0") / (period + 1)

        self._t1 = period
        self._t2 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t >= self._t2:
            self.value = (price - self.value) * self._a + self.value

        return self.value
