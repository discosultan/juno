from collections import deque
from decimal import Decimal
from typing import Sequence


# Least Square Moving Average
class Lsma:
    value: Decimal = Decimal("0.0")

    _prices: deque[Decimal]

    _x: range
    _x_sum: Decimal
    _x2_sum: Decimal
    _divisor: Decimal

    _t: int = 0
    _t1: int

    def __init__(self, period: int = 25) -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

        self._prices = deque(maxlen=period)

        self._x = range(1, period + 1)
        self._x_sum = Decimal("0.5") * period * (period + 1)
        self._x2_sum = self._x_sum * (2 * period + 1) / Decimal("3.0")
        self._divisor = period * self._x2_sum - self._x_sum * self._x_sum

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
            self.value = self._linreg(self._prices)

        return self.value

    # Ref:
    # https://github.com/twopirllc/pandas-ta/blob/development/pandas_ta/overlap/linreg.py
    def _linreg(self, values: Sequence[Decimal]) -> Decimal:
        y_sum = sum(values, Decimal("0.0"))
        xy_sum = sum((a * b for a, b in zip(self._x, values)), Decimal("0.0"))

        m = (self._t1 * xy_sum - self._x_sum * y_sum) / self._divisor
        b = (y_sum * self._x2_sum - self._x_sum * xy_sum) / self._divisor
        return m * self._t1 + b
