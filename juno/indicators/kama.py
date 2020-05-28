from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Deque


# Kaufman's Adaptive Moving Average
class Kama:
    value: Decimal = Decimal('0.0')

    _short_alpha: Decimal
    _long_alpha: Decimal

    # _prev_price: Decimal
    _prices: Deque[Decimal]
    _diffs: Deque[Decimal]

    _t: int = -1
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._short_alpha = Decimal('2.0') / (Decimal('2.0') + 1)
        self._long_alpha = Decimal('2.0') / (Decimal('30.0') + 1)

        self._prices = deque(maxlen=period)
        self._diffs = deque(maxlen=period)

        self._t1 = period - 1
        self._t2 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        if self._t > 0:
            self._diffs.append(abs(price - self._prices[-1]))

        if self._t == self._t1:
            self.value = price
        elif self._t == self._t2:
            diff_sum = sum(self._diffs)
            if diff_sum == 0:
                er = Decimal('1.0')
            else:
                er = abs(price - self._prices[0]) / diff_sum
            sc = (er * (self._short_alpha - self._long_alpha) + self._long_alpha)**2

            self.value += sc * (price - self.value)

        self._prices.append(price)
        return self.value
