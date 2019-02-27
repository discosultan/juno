from decimal import Decimal

from . import Sma


# Smoothed Moving Average
class Smma:

    def __init__(self, period: int):
        self.result = Decimal(0)
        self.sma = Sma(period)
        self.weight = period
        self.t = 0
        self.t1 = period - 1
        self.t2 = period

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, price: Decimal) -> Decimal:
        if self.t < self.t1:
            self.sma.update(price)
        elif self.t == self.t1:
            self.result = self.sma.update(price)
        else:
            self.result = (self.result * (self.weight - 1) + price) / self.weight

        self.t = min(self.t + 1, self.t2)
        return self.result
