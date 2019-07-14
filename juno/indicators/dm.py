from decimal import Decimal
from typing import Tuple


# Directional Movement Indicator
class DM:
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.plus_value = Decimal(0)
        self.minus_value = Decimal(0)

        self._per = (period - 1) / Decimal(period)

        self._dmup = Decimal(0)
        self._dmdown = Decimal(0)
        self._prev_high = Decimal(0)
        self._prev_low = Decimal(0)

        self._t = 0
        self._t1 = 1
        self._t2 = period - 1
        self._t3 = period

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, high: Decimal, low: Decimal) -> None:
        if self._t >= self._t1 and self._t < self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low)
            self._dmup += dp
            self._dmdown += dm

        if self._t == self._t2:
            self.plus_value = self._dmup
            self.minus_value = self._dmdown
        elif self._t == self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low)
            self._dmup = self._dmup * self._per + dp
            self._dmdown = self._dmdown * self._per + dm
            self.plus_value = self._dmup
            self.minus_value = self._dmdown

        self._prev_high = high
        self._prev_low = low
        self._t = min(self._t + 1, self._t3)


def _calc_direction(prev_high: Decimal, prev_low: Decimal, high: Decimal,
                    low: Decimal) -> Tuple[Decimal, Decimal]:
    up = high - prev_high
    down = prev_low - low

    if up < 0:
        up = Decimal(0)
    elif up > down:
        down = Decimal(0)

    if down < 0:
        down = Decimal(0)
    elif down > up:
        up = Decimal(0)

    return up, down
