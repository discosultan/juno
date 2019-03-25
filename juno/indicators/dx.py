from decimal import Decimal

from .di import DI


# Directional Movement Index
class DX:

    def __init__(self, period: int) -> None:
        self.di = DI(period)

        self.t = 0
        self.t1 = period - 1

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        di_up, di_down = self.di.update(high, low, close)

        dx = Decimal(0)
        if self.t == self.t1:
            dm_diff = abs(di_up - di_down)
            dm_sum = di_up + di_down
            dx = dm_diff / dm_sum * 100

        self.t = min(self.t + 1, self.t1)

        return dx
