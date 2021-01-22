from collections import deque
from decimal import Decimal

from .sma import Sma


# Full Stochastic Oscillator
class Stoch:
    k: Decimal = Decimal('0.0')
    d: Decimal = Decimal('0.0')

    _k_high_window: deque[Decimal]
    _k_low_window: deque[Decimal]

    _k_sma: Sma
    _d_sma: Sma

    _t: int = 0
    _t1: int
    _t2: int
    _t3: int

    def __init__(self, k_period: int, k_sma_period: int, d_sma_period: int) -> None:
        if k_period < 1:
            raise ValueError(f'Invalid period ({k_period})')

        self._k_high_window = deque(maxlen=k_period)
        self._k_low_window = deque(maxlen=k_period)

        self._k_sma = Sma(k_sma_period)
        self._d_sma = Sma(d_sma_period)

        self._t1 = k_period
        self._t2 = self._t1 + k_sma_period - 1
        self._t3 = self._t2 + d_sma_period - 1

    @property
    def maturity(self) -> int:
        return self._t3

    @property
    def mature(self) -> bool:
        return self._t >= self._t3

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> tuple[Decimal, Decimal]:
        self._t = min(self._t + 1, self._t3)

        self._k_high_window.append(high)
        self._k_low_window.append(low)

        if self._t >= self._t1:
            max_high = max(self._k_high_window)
            min_low = min(self._k_low_window)
            fast_k = 100 * (close - min_low) / (max_high - min_low)

            self._k_sma.update(fast_k)

            if self._t >= self._t2:
                self._d_sma.update(self._k_sma.value)

            if self._t >= self._t3:
                self.k = self._k_sma.value
                self.d = self._d_sma.value

        return self.k, self.d
