from decimal import Decimal
from statistics import mean

from juno.utils import CircularBuffer


# Simple Moving Average
class Sma:
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value = Decimal(0)
        self._buffer = CircularBuffer(period, Decimal(0))
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        self._buffer.push(price)
        if self._t == self._t1:
            self.value = mean(self._buffer)
        self._t = min(self._t + 1, self._t1)
