from __future__ import annotations  # Required for 'self' annotation

from decimal import Decimal


# Exponential Moving Average
class Ema:

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.a = Decimal(2) / (period + 1)  # Smoothing factor.
        self.result = Decimal(0)
        self.t = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, price: Decimal) -> Decimal:
        if self.t == 0:
            self.result = price
            self.t = 1
        else:
            self.result = (price - self.result) * self.a + self.result

        return self.result

    @staticmethod
    def with_smoothing(a: Decimal) -> Ema:  # noqa
        dummy_period = 1
        ema = Ema(dummy_period)
        ema.a = a
        return ema
