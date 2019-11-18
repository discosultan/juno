from collections import deque
from decimal import Decimal
from typing import Deque

from .adx import Adx


# Average Directional Movement Index Rating
class Adxr:
    def __init__(self, period: int) -> None:
        self.value = Decimal('0.0')
        self._adx = Adx(period)
        self._historical_adx: Deque[Decimal] = deque(maxlen=period)
        self._t = 0
        self._t1 = self._adx.req_history
        self._t2 = self._t1 + period - 1

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        self._adx.update(high, low, close)

        if self._t >= self._t1:
            self._historical_adx.append(self._adx.value)
        if self._t == self._t2:
            self.value = (self._adx.value + self._historical_adx.popleft()) / 2

        self._t = min(self._t + 1, self._t2)
