from decimal import Decimal

from .dx import DX
from .smma import Smma


# Average Directional Index
class Adx:
    value: Decimal = Decimal("0.0")

    _dx: DX
    _smma: Smma

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f"Invalid period ({period})")

        self._dx = DX(period)
        self._smma = Smma(period)

    @property
    def maturity(self) -> int:
        return max(self._dx.maturity, self._smma.maturity)

    @property
    def mature(self) -> bool:
        return self._dx.mature and self._smma.mature

    def update(self, high: Decimal, low: Decimal) -> Decimal:
        self._dx.update(high, low)
        if self._dx.value == 0:
            self.value = Decimal("0.0")
        else:
            self._smma.update(self._dx.value)
            self.value = self._smma.value
        return self.value
