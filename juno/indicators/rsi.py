from decimal import Decimal

from .smma import Smma


# Relative Strength Index
class Rsi:
    value: Decimal = Decimal('0.0')
    _mean_down: Smma
    _mean_up: Smma
    _last_price: Decimal = Decimal('0.0')
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        self._mean_down = Smma(period)
        self._mean_up = Smma(period)
        self._t1 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        if self._t > 1:
            up = Decimal('0.0')
            down = Decimal('0.0')
            if price > self._last_price:
                up = price - self._last_price
            elif price < self._last_price:
                down = self._last_price - price

            self._mean_up.update(up)
            self._mean_down.update(down)

            if self._t == self._t1:
                if self._mean_down.value == 0 and self._mean_up.value != 0:
                    self.value = Decimal('100.0')
                elif self._mean_down.value == 0:
                    self.value = Decimal('0.0')
                else:
                    rs = self._mean_up.value / self._mean_down.value
                    self.value = 100 - (100 / (1 + rs))

        self._last_price = price
        return self.value
