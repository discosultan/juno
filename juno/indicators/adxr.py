from collections import deque
from decimal import Decimal
from typing import Deque

from .adx import Adx


# Average Directional Movement Index Rating
class Adxr:

    def __init__(self, period: int) -> None:
        self.adx = Adx(period)
        self.historical_adx: Deque[Decimal] = deque(maxlen=period)
        self.i = 0
        self.t = 0
        self.t1 = self.adx.req_history
        self.t2 = self.t1 + period - 1

    @property
    def req_history(self) -> int:
        return self.t2

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        adx = self.adx.update(high, low, close)

        result = Decimal(0)

        if self.t >= self.t1:
            self.historical_adx.append(adx)
        if self.t == self.t2:
            result = (adx + self.historical_adx.popleft()) / 2

        self.t = min(self.t + 1, self.t2)

        return result
