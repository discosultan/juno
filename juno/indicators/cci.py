from decimal import Decimal

from .sma import Sma


# Commodity Channel Index
class Cci:

    def __init__(self, period: int):
        self.sma = Sma(period)
        self.scale = Decimal(1) / period
        self.typical_prices = [Decimal(0)] * period
        self.i = 0
        self.t = 0
        self.t1 = (period - 1) * 2

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        typical_price = (high + low + close) / 3

        avg = self.sma.update(typical_price)

        self.typical_prices[self.i] = typical_price
        self.i = (self.i + 1) % len(self.typical_prices)

        result = Decimal(0)

        if self.t == self.t1:

            acc = Decimal(0)
            for i in range(0, len(self.typical_prices)):
                acc += abs(avg - self.typical_prices[i])

            result = acc * self.scale * Decimal('0.015')
            result = (typical_price - avg) / result

        self.t = min(self.t + 1, self.t1)

        return result
