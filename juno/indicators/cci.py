from collections import deque
from decimal import Decimal

from .sma import Sma


# Commodity Channel Index
class Cci:
    value: Decimal = Decimal("0.0")

    _sma: Sma
    _scale: Decimal
    _typical_prices: deque[Decimal]
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        self._sma = Sma(period)
        self._scale = Decimal("1.0") / period
        self._typical_prices = deque(maxlen=period)
        self._t1 = period * 2 - 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        typical_price = (high + low + close) / 3
        self._typical_prices.append(typical_price)
        self._sma.update(typical_price)

        if self._t == self._t1:
            acc = sum(abs(self._sma.value - tp) for tp in self._typical_prices)
            self.value = (typical_price - self._sma.value) / (acc * self._scale * Decimal("0.015"))

        return self.value
