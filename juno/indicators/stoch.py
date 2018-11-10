from . import Sma


# Full Stochastic Oscillator
class Stoch:

    def __init__(self, k_period, k_sma_period, d_sma_period):
        if k_period < 1:
            raise ValueError(f'invalid period ({k_period})')

        self.i = 0
        self.k_high_window = [0.0] * k_period
        self.k_low_window = [0.0] * k_period

        self.k_sma = Sma(k_sma_period)
        self.d_sma = Sma(d_sma_period)

        self.t = 0
        self.t1 = k_period - 1
        self.t2 = self.t1 + k_sma_period - 1
        self.t3 = self.t2 + d_sma_period - 1

    @property
    def req_history(self):
        return self.t3

    def update(self, high, low, close):

        self.k_high_window[self.i] = high
        self.k_low_window[self.i] = low
        self.i = (self.i + 1) % len(self.k_high_window)

        full_k, full_d = None, None
        if self.t >= self.t1:
            max_high = max(self.k_high_window)
            min_low = min(self.k_low_window)
            fast_k = 100.0 * (close - min_low) / (max_high - min_low)

            full_k = self.k_sma.update(fast_k)
            full_d = self.d_sma.update(full_k) if self.t >= self.t2 else None
            full_k, full_d = (full_k, full_d) if self.t == self.t3 else (None, None)

        self.t = min(self.t + 1, self.t3)

        return full_k, full_d
