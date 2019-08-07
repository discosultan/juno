from decimal import Decimal
from typing import Generic, Type, TypeVar

from .smma import Smma

T = TypeVar('T', float, Decimal)


# Relative Strength Index
class Rsi(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._mean_down: Smma[T] = Smma(period, dec=dec)
        self._mean_up: Smma[T] = Smma(period, dec=dec)
        self._last_input: T = dec(0)
        self._t = 0
        self._t1 = period
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: T) -> None:
        if self._t > 0:
            up = self._dec(0)
            down = self._dec(0)
            if price > self._last_input:
                up = price - self._last_input
            elif price < self._last_input:
                down = self._last_input - price

            self._mean_up.update(up)
            self._mean_down.update(down)

            if self._t == self._t1:
                if self._mean_down.value == 0 and self._mean_up.value != 0:
                    self.value = self._dec(100)
                elif self._mean_down.value == 0:
                    self.value = self._dec(0)
                else:
                    rs = self._mean_up.value / self._mean_down.value
                    self.value = 100 - (100 / (1 + rs))

        self._last_input = price
        self._t = min(self._t + 1, self._t1)
