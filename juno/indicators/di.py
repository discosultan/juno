from decimal import Decimal

from .dm import DM


# Directional Indicator
class DI:
    plus_value: Decimal = Decimal('0.0')
    minus_value: Decimal = Decimal('0.0')

    _dm: DM
    _atr: Decimal = Decimal('0.0')
    _per: Decimal

    _prev_close: Decimal = Decimal('0.0')

    _t: int = 0
    _t1: int = 2
    _t2: int
    _t3: int

    def __init__(self, period: int) -> None:
        self._dm = DM(period)
        self._per = (period - 1) / Decimal(period)

        self._t2 = period
        self._t3 = period + 1

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> tuple[Decimal, Decimal]:
        self._t = min(self._t + 1, self._t3)

        self._dm.update(high, low)

        if self._t >= self._t1 and self._t < self._t3:
            self._atr += _calc_truerange(self._prev_close, high, low)

        if self._t == self._t2:
            self.plus_value = 100 * self._dm.plus_value / self._atr
            self.minus_value = 100 * self._dm.minus_value / self._atr
        elif self._t >= self._t3:
            self._atr = self._atr * self._per + _calc_truerange(self._prev_close, high, low)
            self.plus_value = 100 * self._dm.plus_value / self._atr
            self.minus_value = 100 * self._dm.minus_value / self._atr

        self._prev_close = close
        return self.plus_value, self.minus_value


def _calc_truerange(prev_close: Decimal, high: Decimal, low: Decimal) -> Decimal:
    ych = abs(high - prev_close)
    ycl = abs(low - prev_close)
    v = high - low
    if ych > v:
        v = ych
    if ycl > v:
        v = ycl
    return v
