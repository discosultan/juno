from __future__ import annotations

import itertools
from collections import deque
from decimal import Decimal
from statistics import median
from typing import Deque


# Market Meanness Index
# TODO: Double check
class Mmi:
    value: Decimal = Decimal('0.0')

    _prices: Deque[Decimal]

    _t: int = -1
    _t1: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._prices = deque(maxlen=period)

        self._t1 = period - 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)
        self._prices.append(price)

        if self.mature:
            med = median(self._prices)
            td = 0
            th = 0
            prev_price = self._prices[0]
            for next_price in itertools.islice(self._prices, 1, len(self._prices)):
                if prev_price < med and next_price > prev_price:
                    th += 1
                if prev_price > med and next_price < prev_price:
                    td += 1
                prev_price = next_price
            self.value = Decimal('100.0') * (th + td) / self._t1

        return self.value
