from decimal import Decimal

from .dm import DM


# Directional Indicator
class DI:
    def __init__(self, period: int) -> None:
        self.plus_value = Decimal(0)
        self.minus_value = Decimal(0)

        self._dm = DM(period)
        self._atr = Decimal(0)
        self._per = (period - 1) / Decimal(period)

        self._prev_close = Decimal(0)

        self._t = 0
        self._t1 = 1
        self._t2 = period - 1
        self._t3 = period

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
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


def _calc_truerange(prev_close: Decimal, high: Decimal, low: Decimal) -> Decimal:
    ych = abs(high - prev_close)
    ycl = abs(low - prev_close)
    v = high - low
    if ych > v:
        v = ych
    if ycl > v:
        v = ycl
    return v
