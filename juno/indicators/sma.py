from decimal import Decimal
from statistics import mean

from juno.utils import CircularBuffer


# Simple Moving Average
class Sma:

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.buffer = CircularBuffer(period, Decimal(0))
        self.t = 0
        self.t1 = period - 1

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, price: Decimal) -> Decimal:
        self.buffer.push(price)
        result = mean(self.buffer) if self.t == self.t1 else Decimal(0)

        self.t = min(self.t + 1, self.t1)
        return result
