from decimal import Decimal
from typing import Generic, Type, TypeVar

from .dm import DM

T = TypeVar('T', float, Decimal)


# Directional Indicator
class DI(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.plus_value: T = dec(0)
        self.minus_value: T = dec(0)

        self._dm: DM[T] = DM(period, dec=dec)
        self._atr: T = dec(0)
        self._per: T = (period - 1) / dec(period)

        self._prev_close: T = dec(0)

        self._t = 0
        self._t1 = 1
        self._t2 = period - 1
        self._t3 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: T, low: T, close: T) -> None:
        self._dm.update(high, low)

        if self._t >= self._t1 and self._t < self._t3:
            self._atr += _calc_truerange(self._prev_close, high, low)

        if self._t == self._t2:
            self.plus_value = 100 * self._dm.plus_value / self._atr
            self.minus_value = 100 * self._dm.minus_value / self._atr
        elif self._t == self._t3:
            self._atr = self._atr * self._per + _calc_truerange(self._prev_close, high, low)
            self.plus_value = 100 * self._dm.plus_value / self._atr
            self.minus_value = 100 * self._dm.minus_value / self._atr

        self._prev_close = close
        self._t = min(self._t + 1, self._t3)


def _calc_truerange(prev_close: T, high: T, low: T) -> T:
    ych = abs(high - prev_close)
    ycl = abs(low - prev_close)
    v = high - low
    if ych > v:
        v = ych
    if ycl > v:
        v = ycl
    return v
