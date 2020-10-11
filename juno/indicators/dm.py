from decimal import Decimal
from typing import Tuple


# Directional Movement Indicator
class DM:
    plus_value: Decimal = Decimal('0.0')
    minus_value: Decimal = Decimal('0.0')

    _per: Decimal

    _dmup: Decimal = Decimal('0.0')
    _dmdown: Decimal = Decimal('0.0')
    _prev_high: Decimal = Decimal('0.0')
    _prev_low: Decimal = Decimal('0.0')

    _t: int = 0
    _t1: int = 2
    _t2: int
    _t3: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self._per = (period - 1) / Decimal(period)

        self._t2 = period
        self._t3 = period + 1

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    @property
    def diff(self) -> Decimal:
        return abs(self.plus_value - self.minus_value)

    @property
    def sum(self) -> Decimal:
        return self.plus_value + self.minus_value

    def update(self, high: Decimal, low: Decimal) -> Tuple[Decimal, Decimal]:
        self._t = min(self._t + 1, self._t3)

        if self._t >= self._t1 and self._t < self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low)
            self._dmup += dp
            self._dmdown += dm

        if self._t == self._t2:
            self.plus_value = self._dmup
            self.minus_value = self._dmdown
        elif self._t >= self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low)
            self._dmup = self._dmup * self._per + dp
            self._dmdown = self._dmdown * self._per + dm
            self.plus_value = self._dmup
            self.minus_value = self._dmdown

        self._prev_high = high
        self._prev_low = low
        return self.plus_value, self.minus_value


def _calc_direction(prev_high: Decimal, prev_low: Decimal, high: Decimal,
                    low: Decimal) -> Tuple[Decimal, Decimal]:
    up = high - prev_high
    down = prev_low - low

    if up < 0:
        up = Decimal('0.0')
    elif up > down:
        down = Decimal('0.0')

    if down < 0:
        down = Decimal('0.0')
    elif down > up:
        up = Decimal('0.0')

    return up, down
