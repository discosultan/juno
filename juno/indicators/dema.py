from decimal import Decimal

from .ema import Ema


# Double Exponential Moving Average
class Dema:
    value: Decimal = Decimal('0.0')
    _ema1: Ema
    _ema2: Ema
    _t: int = -1
    _t1: int
    _t2: int

    def __init__(self, period: int) -> None:
        self._ema1 = Ema(period)
        self._ema2 = Ema(period)
        self._t1 = period - 1
        self._t2 = self._t1 * 2

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)
        self._ema1.update(price)

        if self._t <= self._t1:
            self._ema2.update(price)

        if self._t >= self._t1:
            self._ema2.update(self._ema1.value)
            if self._t == self._t2:
                self.value = self._ema1.value * Decimal('2.0') - self._ema2.value

        return self.value
