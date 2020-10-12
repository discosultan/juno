from decimal import Decimal

from .sma import Sma


# Smoothed Moving Average
class Smma:
    value: Decimal = Decimal('0.0')
    _sma: Sma
    _weight: int
    _t: int = 0
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        self._sma = Sma(period)
        self._weight = period
        self._t1 = period
        self._t2 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t >= self._t2:
            self.value = (self.value * (self._weight - 1) + price) / self._weight

        return self.value
