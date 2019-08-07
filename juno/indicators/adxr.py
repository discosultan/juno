from collections import deque
from decimal import Decimal
from typing import Deque, Generic, Type, TypeVar

from .adx import Adx

T = TypeVar('T', float, Decimal)


# Average Directional Movement Index Rating
class Adxr(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._adx: Adx[T] = Adx(period, dec=dec)
        self._historical_adx: Deque[T] = deque(maxlen=period)
        self._t = 0
        self._t1 = self._adx.req_history
        self._t2 = self._t1 + period - 1

    @property
    def req_history(self) -> int:
        return self._t2

    def update(self, high: T, low: T, close: T) -> None:
        self._adx.update(high, low, close)

        if self._t >= self._t1:
            self._historical_adx.append(self._adx.value)
        if self._t == self._t2:
            self.value = (self._adx.value + self._historical_adx.popleft()) / 2

        self._t = min(self._t + 1, self._t2)
