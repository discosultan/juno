from __future__ import annotations

from decimal import Decimal

from juno.utils import CircularBuffer

from .rsi import Rsi


# Stochastic Relative Strength Index
class StochRsi:

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f'invalid period ({period})')

        self.rsi = Rsi(period)
        self.t = 0
        self.t1 = period
        self.t2 = period * 2 - 1
        self.min = Decimal(0)
        self.max = Decimal(0)
        self.rsi_values = CircularBuffer(period, Decimal(0))

    @property
    def req_history(self) -> int:
        return self.t2

    def update(self, price: Decimal) -> Decimal:
        result = self.rsi.update(price)

        if self.t >= self.t1:
            self.rsi_values.push(result)

        if self.t == self.t2:
            self.min = min(self.rsi_values)
            self.max = max(self.rsi_values)
            diff = self.max - self.min
            if diff == Decimal(0):
                result = Decimal(0)
            else:
                result = (result - self.min) / diff
        else:
            result = Decimal(0)

        self.last_input = price
        self.t = min(self.t + 1, self.t2)
        return result
