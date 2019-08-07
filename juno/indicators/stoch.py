from decimal import Decimal
from typing import Generic, Type, TypeVar

from juno.utils import CircularBuffer

from .sma import Sma

T = TypeVar('T', float, Decimal)


# Full Stochastic Oscillator
class Stoch(Generic[T]):
    def __init__(self, k_period: int, k_sma_period: int, d_sma_period: int,  # type: ignore
                 dec: Type[T] = Decimal) -> None:
        if k_period < 1:
            raise ValueError(f'Invalid period ({k_period})')

        self.k: T = dec(0)
        self.d: T = dec(0)

        self._k_high_window: CircularBuffer[T] = CircularBuffer(k_period, dec(0))
        self._k_low_window: CircularBuffer[T] = CircularBuffer(k_period, dec(0))

        self._k_sma: Sma[T] = Sma(k_sma_period, dec=dec)
        self._d_sma: Sma[T] = Sma(d_sma_period, dec=dec)

        self._t = 0
        self._t1 = k_period - 1
        self._t2 = self._t1 + k_sma_period - 1
        self._t3 = self._t2 + d_sma_period - 1

    @property
    def req_history(self) -> int:
        return self._t3

    def update(self, high: T, low: T, close: T) -> None:
        self._k_high_window.push(high)
        self._k_low_window.push(low)

        if self._t >= self._t1:
            max_high = max(self._k_high_window)
            min_low = min(self._k_low_window)
            fast_k = 100 * (close - min_low) / (max_high - min_low)

            self._k_sma.update(fast_k)

            if self._t >= self._t2:
                self._d_sma.update(self._k_sma.value)

            if self._t == self._t3:
                self.k = self._k_sma.value
                self.d = self._d_sma.value

        self._t = min(self._t + 1, self._t3)
