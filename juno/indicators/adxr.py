from collections import deque
from decimal import Decimal

from .adx import Adx


# Average Directional Movement Index Rating
class Adxr:
    value: Decimal = Decimal("0.0")

    _adx: Adx
    _historical_adx: deque[Decimal]
    _t: int = 0
    _t1: int
    _t2: int
    _t3: int

    def __init__(self, period: int) -> None:
        self._adx = Adx(period)
        self._historical_adx = deque(maxlen=period)
        self._t1 = self._adx.maturity
        self._t2 = self._t1 + period - 1
        self._t3 = period * 3 - 2

    @property
    def maturity(self) -> int:
        return self._t3

    @property
    def mature(self) -> bool:
        return self._t >= self._t3

    def update(self, high: Decimal, low: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t3)

        self._adx.update(high, low)

        if self._t >= self._t1:
            self._historical_adx.append(self._adx.value)
        if self._t >= self._t2:
            self.value = (self._adx.value + self._historical_adx.popleft()) / 2

        return self.value
