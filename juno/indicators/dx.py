from decimal import Decimal

from .dm import DM


# Directional Movement Index
class DX:
    value: Decimal = Decimal("0.0")

    _dm: DM
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        self._dm = DM(period)
        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, high: Decimal, low: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        self._dm.update(high, low)

        if self._t >= self._t1:
            self.value = self._dm.diff / self._dm.sum * 100

        return self.value
