from __future__ import annotations

from collections import deque
from decimal import Decimal

from .rsi import Rsi


# Stochastic Relative Strength Index
class StochRsi:
    value: Decimal = Decimal("0.0")

    _rsi: Rsi
    _min: Decimal = Decimal("0.0")
    _max: Decimal = Decimal("0.0")
    _rsi_values: deque[Decimal]
    _t: int = 0
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f"Invalid period ({period})")

        self._rsi = Rsi(period)
        self._rsi_values = deque(maxlen=period)
        self._t1 = period + 1
        self._t2 = period * 2

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        self._rsi.update(price)

        if self._t >= self._t1:
            self._rsi_values.append(self._rsi.value)

        if self._t >= self._t2:
            self._min = min(self._rsi_values)
            self._max = max(self._rsi_values)
            diff = self._max - self._min
            if diff == 0:
                self.value = Decimal("0.0")
            else:
                self.value = (self._rsi.value - self._min) / diff

        return self.value
