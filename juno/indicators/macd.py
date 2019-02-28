from decimal import Decimal
from typing import Tuple

from .ema import Ema


# Moving Average Convergence Divergence
class Macd:

    def __init__(self, short_period: int, long_period: int, signal_period: int):
        if short_period < 1 or long_period < 2 or signal_period < 1:
            raise ValueError(f'invalid period(s) ({short_period}, {long_period}, {signal_period})')
        if long_period < short_period:
            raise ValueError(f'long period ({long_period}) must be larger '
                             f'than or equal to short period ({short_period})')

        # A bit hacky but is what is usually expected.
        if short_period == 12 and long_period == 26:
            self.short_ema = Ema.with_smoothing(Decimal('0.15'))
            self.long_ema = Ema.with_smoothing(Decimal('0.075'))
        else:
            self.short_ema = Ema(short_period)
            self.long_ema = Ema(long_period)

        self.signal_ema = Ema(signal_period)

        self.t = 0
        self.t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, price: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
        short_ema_result = self.short_ema.update(price)
        long_ema_result = self.long_ema.update(price)

        macd, signal, divergence = Decimal(0), Decimal(0), Decimal(0)

        if self.t == self.t1:
            macd = short_ema_result - long_ema_result
            signal = self.signal_ema.update(macd)
            divergence = macd - signal

        self.t = min(self.t + 1, self.t1)

        return macd, signal, divergence
