from decimal import Decimal

from .dx import DX
from .smma import Smma


# Average Directional Index
class Adx:

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f'invalid period ({period})')

        self.dx = DX(period)
        self.smma = Smma(period)
        self.t1 = (period - 1) * 2

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        dx = self.dx.update(high, low, close)
        return Decimal(0) if dx == 0 else self.smma.update(dx)
