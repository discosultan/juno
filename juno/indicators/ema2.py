from __future__ import annotations

from decimal import Decimal

from .sma import Sma


# Exponential Moving Average
class Ema2:

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.sma = Sma(period)

        self.a = Decimal(2) / (period + 1)  # Smoothing factor.
        self.result = Decimal(0)
        self.t = 0
        self.t1 = period - 1
        self.flag = False

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, price: Decimal) -> Decimal:
        if self.t < self.t1:
            self.sma.update(price)

        if self.t == self.t1:
            if not self.flag:
                self.result = self.sma.update(price)
                self.flag = True
            else:
                self.result = (price - self.result) * self.a + self.result

        self.t = min(self.t + 1, self.t1)
        return self.result

    @staticmethod
    def with_smoothing(a: Decimal) -> Ema2:  # noqa
        dummy_period = 1
        ema = Ema2(dummy_period)
        ema.a = a
        return ema
