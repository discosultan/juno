from decimal import Decimal
from typing import Generic, Type, TypeVar

from .dx import DX
from .smma import Smma

T = TypeVar('T', float, Decimal)


# Average Directional Index
class Adx(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        if period < 2:
            raise ValueError(f'Invalid period ({period})')

        self.value: T = dec(0)
        self._dx: DX[T] = DX(period, dec=dec)
        self._smma: Smma[T] = Smma(period, dec=dec)
        self._t1 = (period - 1) * 2
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: T, low: T, close: T) -> None:
        self._dx.update(high, low, close)
        if self._dx.value == 0:
            self.value = self._dec(0)
        else:
            self._smma.update(self._dx.value)
            self.value = self._smma.value
