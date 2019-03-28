from decimal import Decimal

from .sma import Sma


# Full Stochastic Oscillator
class Stoch:

    def __init__(self, k_period: int, k_sma_period: int, d_sma_period: int) -> None:
        if k_period < 1:
            raise ValueError(f'invalid period ({k_period})')

        self.k = Decimal(0)
        self.d = Decimal(0)

        self._i = 0
        self._k_high_window = [Decimal(0)] * k_period
        self._k_low_window = [Decimal(0)] * k_period

        self._k_sma = Sma(k_sma_period)
        self._d_sma = Sma(d_sma_period)

        self._t = 0
        self._t1 = k_period - 1
        self._t2 = self._t1 + k_sma_period - 1
        self._t3 = self._t2 + d_sma_period - 1

    @property
    def req_history(self) -> int:
        return self._t3

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        self._k_high_window[self._i] = high
        self._k_low_window[self._i] = low
        self._i = (self._i + 1) % len(self._k_high_window)

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
