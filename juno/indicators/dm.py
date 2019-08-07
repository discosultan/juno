from decimal import Decimal
from typing import Generic, Tuple, Type, TypeVar

T = TypeVar('T', float, Decimal)


# Directional Movement Indicator
class DM(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.plus_value: T = dec(0)
        self.minus_value: T = dec(0)

        self._per: T = (period - 1) / dec(period)

        self._dmup: T = dec(0)
        self._dmdown: T = dec(0)
        self._prev_high: T = dec(0)
        self._prev_low: T = dec(0)

        self._t = 0
        self._t1 = 1
        self._t2 = period - 1
        self._t3 = period
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, high: T, low: T) -> None:
        if self._t >= self._t1 and self._t < self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low, self._dec)
            self._dmup += dp
            self._dmdown += dm

        if self._t == self._t2:
            self.plus_value = self._dmup
            self.minus_value = self._dmdown
        elif self._t == self._t3:
            dp, dm = _calc_direction(self._prev_high, self._prev_low, high, low, self._dec)
            self._dmup = self._dmup * self._per + dp
            self._dmdown = self._dmdown * self._per + dm
            self.plus_value = self._dmup
            self.minus_value = self._dmdown

        self._prev_high = high
        self._prev_low = low
        self._t = min(self._t + 1, self._t3)


def _calc_direction(prev_high: T, prev_low: T, high: T, low: T, dec: Type[T]) -> Tuple[T, T]:
    up = high - prev_high
    down = prev_low - low

    if up < 0:
        up = dec(0)
    elif up > down:
        down = dec(0)

    if down < 0:
        down = dec(0)
    elif down > up:
        up = dec(0)

    return up, down
