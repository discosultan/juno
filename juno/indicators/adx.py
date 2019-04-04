from decimal import Decimal

from .dx import DX
from .smma import Smma


# Average Directional Index
class Adx:

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f'Invalid period ({period})')

        self.value = Decimal(0)
        self._dx = DX(period)
        self._smma = Smma(period)
        self._t1 = (period - 1) * 2

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        self._dx.update(high, low, close)
        if self._dx.value == 0:
            self.value = Decimal(0)
        else:
            self._smma.update(self._dx.value)
            self.value = self._smma.value
