from collections import deque
from decimal import Decimal


# Weighted Moving Average
class Wma:
    value: Decimal = Decimal("0.0")

    _prices: deque[Decimal]
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

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
            norm = Decimal("0.0")
            sum = Decimal("0.0")
            for i in range(self._t1):
                weight = (self._t1 - i) * self._t1
                norm += weight
                sum += self._prices[len(self._prices) - i - 1] * weight
            self.value = sum / norm

        return self.value
