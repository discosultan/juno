from __future__ import annotations

from decimal import Decimal


# Exponential Moving Average
class Ema:

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.value = Decimal(0)
        self._a = Decimal(2) / (period + 1)  # Smoothing factor.
        self._t = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, price: Decimal) -> None:
        if self._t == 0:
            self.value = price
            self._t = 1
        else:
            self.value = (price - self.value) * self._a + self.value

    @staticmethod
    def with_smoothing(a: Decimal) -> Ema:  # noqa
        dummy_period = 1
        ema = Ema(dummy_period)
        ema._a = a
        return ema
