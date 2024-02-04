from collections import deque
from decimal import Decimal
from typing import Iterable

from .sma import Sma


# Commodity Channel Index from TradingView
class Cci2:
    value: Decimal = Decimal("0.0")

    _sma: Sma
    _scale: Decimal
    _prices: deque[Decimal]
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        self._sma = Sma(period)
        self._scale = Decimal("1.0") / period
        self._prices = deque(maxlen=period)
        self._t1 = period * 2 - 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        self._prices.append(price)
        self._sma.update(price)

        if self._t == self._t1:
            acc = sum(abs(self._sma.value - tp) for tp in self._prices)
            self.value = (price - self._sma.value) / (acc * self._scale * Decimal("0.015"))

        return self.value

    @staticmethod
    def for_period(prices: Iterable[Decimal], period: int) -> Decimal:
        cci = Cci2(period)
        for price in prices:
            cci.update(price)
        return cci.value
