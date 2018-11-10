from . import Sma
from math import sqrt

# Commodity Channel Index
class Cci:

    def __init__(self, period):
        self.sma = Sma(period)
        self.scale = 1.0 / period
        self.typical_prices = [0.0] * period
        self.i = 0
        self.t = 0
        self.t1 = (period - 1) * 2

    @property
    def req_history(self):
        return self.t1

    def update(self, high, low, close):
        typical_price = (high + low + close) / 3.0

        avg = self.sma.update(typical_price)

        self.typical_prices[self.i] = typical_price
        self.i = (self.i + 1) % len(self.typical_prices)

        result = None

        if self.t == self.t1:

            acc = 0.0
            for i in range(0, len(self.typical_prices)):
                acc += abs(avg - self.typical_prices[i])

            result = acc * self.scale * 0.015
            result = (typical_price - avg) / result

        self.t = min(self.t + 1, self.t1)

        return result
