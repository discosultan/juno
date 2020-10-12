from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Deque

from more_itertools import pairwise


# Momersion Indicator.
# When the Momersion(n) indicator is below the 50% line, price action is dominated by
# mean-reversion and when it is above it, it is dominated by momentum.
class Momersion:
    value: Decimal = Decimal('0.0')

    _prev_price: Decimal = Decimal('0.0')
    _returns: Deque[Decimal]

    _t: int = 0
    _t1: int

    # Common period of 250.
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._returns = deque(maxlen=period - 1)

        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        if self._t > 1:
            self._returns.append(price - self._prev_price)

            if self.mature:
                mc = 0
                mrc = 0
                for prev_ret, next_ret in pairwise(self._returns):
                    if prev_ret * next_ret > 0:
                        mc += 1
                    else:
                        mrc += 1
                self.value = Decimal('100.0') * mc / (mc + mrc)

        self._prev_price = price
        return self.value
