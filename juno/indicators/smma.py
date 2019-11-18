from decimal import Decimal

from .sma import Sma


# Smoothed Moving Average
class Smma:
    def __init__(self, period: int) -> None:
        self.value = Decimal('0.0')
        self._sma = Sma(period)
        self._weight = period
        self._t = 0
        self._t1 = period - 1
        self._t2 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t == self._t2:
            self.value = (self.value * (self._weight - 1) + price) / self._weight

        self._t = min(self._t + 1, self._t2)
