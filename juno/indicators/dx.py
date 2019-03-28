from decimal import Decimal

from .di import DI


# Directional Movement Index
class DX:

    def __init__(self, period: int) -> None:
        self.value = Decimal(0)
        self._di = DI(period)
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        self._di.update(high, low, close)

        if self._t == self._t1:
            dm_diff = abs(self._di.plus_value - self._di.minus_value)
            dm_sum = self._di.plus_value + self._di.minus_value
            self.value = dm_diff / dm_sum * 100

        self._t = min(self._t + 1, self._t1)
