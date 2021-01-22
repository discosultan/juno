from __future__ import annotations

from collections import deque
from decimal import ROUND_FLOOR, Decimal
from typing import Optional


# Arnaud Legoux Moving Average
class Alma:
    value: Decimal = Decimal('0.0')

    _weights: list[Decimal]
    _prices: deque[Decimal]

    _t: int = 0
    _t1: int

    def __init__(
        self, period: int, sigma: Optional[int] = None, offset: Decimal = Decimal('0.85')
    ) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')
        if offset < 0 or offset > 1:
            raise ValueError(f'Invalid offset ({offset})')
        if sigma == 0:
            raise ValueError(f'Invalid sigma ({sigma})')

        sig = int(period / Decimal('1.5')) if sigma is None else sigma

        m = (offset * (period - 1)).to_integral_exact(rounding=ROUND_FLOOR)
        s = period * Decimal('1.0') / sig
        tmp = [(-(i - m) * (i - m) / (2 * s * s)).exp() for i in range(period)]
        sw = sum(tmp)
        self._weights = [w / sw for w in tmp]

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

        if self.mature:
            self.value = sum((p * w for p, w in zip(self._prices, self._weights)), Decimal('0.0'))

        return self.value
