from decimal import Decimal

from juno.utils import CircularBuffer

from .sma import Sma


# Commodity Channel Index
class Cci:

    def __init__(self, period: int) -> None:
        self.value = Decimal(0)
        self._sma = Sma(period)
        self._scale = Decimal(1) / period
        self._typical_prices = CircularBuffer(period, Decimal(0))
        self._t = 0
        self._t1 = (period - 1) * 2

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        typical_price = (high + low + close) / 3
        self._typical_prices.push(typical_price)
        self._sma.update(typical_price)

        if self._t == self._t1:
            acc = sum((abs(self._sma.value - tp) for tp in self._typical_prices))
            self.value = (typical_price - self._sma.value) / (acc * self._scale * Decimal('0.015'))

        self._t = min(self._t + 1, self._t1)
