from __future__ import annotations

from decimal import Decimal
from typing import List

from .sma import Sma


# Exponential Moving Average
class Ema:
    value: Decimal = Decimal('0.0')
    _a: Decimal
    _adjust: bool
    _prices: List[Decimal]  # Only used when `adjust=True`.
    _t: int = 0

    def __init__(self, period: int, adjust: bool = False) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._adjust = adjust
        if adjust:
            self._prices = []
        # Smoothing factor. Decay calculated in terms of span.
        self._a = Decimal('2.0') / (period + 1)  # Smoothing factor.

    @property
    def req_history(self) -> int:
        return 0

    def update(self, price: Decimal) -> None:
        if self._adjust:
            self._prices.append(price)
            numerator = sum(
                ((1 - self._a)**i * p for i, p in enumerate(reversed(self._prices))),
                Decimal('0.0'),
            )
            # TODO: We can optimize denominator.
            denominator = sum(
                ((1 - self._a)**i for i in range(len(self._prices))),
                Decimal('0.0'),
            )
            self.value = numerator / denominator
        else:
            if self._t == 0:
                self.value = price
            else:
                self.value += (price - self.value) * self._a
        self._t += 1

    @staticmethod
    def with_smoothing(a: Decimal, adjust: bool = False) -> Ema:
        ema = Ema(1, adjust=adjust)  # Dummy period.
        ema._a = a
        return ema

    @staticmethod
    def with_com(com: int, adjust: bool = False) -> Ema:
        if com < 0:
            raise ValueError(f'Invalid center of mass ({com})')

        ema = Ema(1, adjust=adjust)
        # Decay calculated in terms of center of mass.
        ema._a = Decimal('1.0') / (1 + com)
        return ema


class Ema2(Ema):
    _sma: Sma
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._sma = Sma(period)
        self._t1 = period - 1
        self._t2 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        if self._t <= self._t1:
            self._sma.update(price)

        if self._t == self._t1:
            self.value = self._sma.value
        elif self._t == self._t2:
            self.value = (price - self.value) * self._a + self.value

        self._t = min(self._t + 1, self._t2)
