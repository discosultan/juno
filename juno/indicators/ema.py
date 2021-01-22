from __future__ import annotations

from decimal import Decimal


# Exponential Moving Average
class Ema:
    value: Decimal = Decimal('0.0')
    _adjust: bool
    _a: Decimal
    _a_inv: Decimal

    # Only used when `adjust=True`.
    _prices: list[Decimal]
    _denominator: Decimal = Decimal('0.0')

    _t: int = 0
    _t1: int

    def __init__(self, period: int, adjust: bool = False) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._adjust = adjust
        if adjust:
            self._prices = []
        # Decay calculated in terms of span.
        self.set_smoothing_factor(Decimal('2.0') / (period + 1))
        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def set_smoothing_factor(self, a: Decimal) -> None:
        self._a = a
        self._a_inv = 1 - self._a

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        if self._adjust:
            self._prices.append(price)
            numerator = sum(
                (self._a_inv**i * p for i, p in enumerate(reversed(self._prices))),
                Decimal('0.0'),
            )
            # self._denominator = sum(
            #     (self._a_inv**i for i in range(len(self._prices))),
            #     Decimal('0.0'),
            # )
            self._denominator += self._a_inv**(len(self._prices) - 1)
            self.value = numerator / self._denominator
        else:
            if self._t == 1:
                self.value = price
            else:
                self.value += (price - self.value) * self._a

        return self.value

    @staticmethod
    def with_smoothing(period: int, a: Decimal, adjust: bool = False) -> Ema:
        ema = Ema(period, adjust=adjust)  # Dummy period.
        ema.set_smoothing_factor(a)
        return ema

    @staticmethod
    def with_com(com: int, adjust: bool = False) -> Ema:
        if com < 0:
            raise ValueError(f'Invalid center of mass ({com})')

        ema = Ema(1, adjust=adjust)
        # Decay calculated in terms of center of mass.
        ema.set_smoothing_factor(Decimal('1.0') / (1 + com))
        return ema
