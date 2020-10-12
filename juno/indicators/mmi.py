from __future__ import annotations

from collections import deque
from decimal import Decimal
from statistics import median
from typing import Deque

from more_itertools import pairwise


# Market Meanness Index
class Mmi:
    value: Decimal = Decimal('0.0')

    _prices: Deque[Decimal]

    _t: int = 0
    _t1: int

    # Common periods are between 200 - 500.
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._prices = deque(maxlen=period)

        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        self._prices.append(price)

        if self._t >= self._t1:
            med = median(self._prices)
            nh = 0
            nl = 0
            for prev_price, next_price in pairwise(self._prices):
                if next_price > med and next_price > prev_price:
                    nl += 1
                if next_price < med and next_price < prev_price:
                    nh += 1
            self.value = Decimal('100.0') * (nl + nh) / (self._t1 - 1)

        return self.value
