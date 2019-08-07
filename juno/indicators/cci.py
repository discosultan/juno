from decimal import Decimal
from typing import Generic, Type, TypeVar

from juno.utils import CircularBuffer

from .sma import Sma

T = TypeVar('T', float, Decimal)


# Commodity Channel Index
class Cci(Generic[T]):
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        self.value: T = dec(0)
        self._sma: Sma[T] = Sma(period, dec=dec)
        self._scale: T = dec(1) / period
        self._typical_prices: CircularBuffer[T] = CircularBuffer(period, dec(0))
        self._t = 0
        self._t1 = (period - 1) * 2
        self._dec: Type[T] = dec

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, high: T, low: T, close: T) -> None:
        typical_price = (high + low + close) / 3
        self._typical_prices.push(typical_price)
        self._sma.update(typical_price)

        if self._t == self._t1:
            acc = sum((abs(self._sma.value - tp) for tp in self._typical_prices))
            self.value = (typical_price - self._sma.value) / (acc * self._scale * self._dec('0.015'))

        self._t = min(self._t + 1, self._t1)
