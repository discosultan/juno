from decimal import Decimal

from .smma import Smma


# Relative Strength Index
class Rsi:

    def __init__(self, period: int) -> None:
        self.value = Decimal(0)
        self._mean_down = Smma(period)
        self._mean_up = Smma(period)
        self._last_input = Decimal(0)
        self._t = 0
        self._t1 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        if self._t > 0:
            up = Decimal(0)
            down = Decimal(0)
            if price > self._last_input:
                up = price - self._last_input
            elif price < self._last_input:
                down = self._last_input - price

            self._mean_up.update(up)
            self._mean_down.update(down)

            if self._t == self._t1:
                if self._mean_down.value == 0 and self._mean_up.value != 0:
                    self.value = Decimal(100)
                elif self._mean_down.value == 0:
                    self.value = Decimal(0)
                else:
                    rs = self._mean_up.value / self._mean_down.value
                    self.value = 100 - (100 / (1 + rs))

        self._last_input = price
        self._t = min(self._t + 1, self._t1)
