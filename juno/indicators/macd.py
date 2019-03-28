from decimal import Decimal

from .ema import Ema


# Moving Average Convergence Divergence
class Macd:

    def __init__(self, short_period: int, long_period: int, signal_period: int) -> None:
        if short_period < 1 or long_period < 2 or signal_period < 1:
            raise ValueError(f'invalid period(s) ({short_period}, {long_period}, {signal_period})')
        if long_period < short_period:
            raise ValueError(f'long period ({long_period}) must be larger '
                             f'than or equal to short period ({short_period})')

        self.value = Decimal(0)
        self.signal = Decimal(0)
        self.divergence = Decimal(0)

        # A bit hacky but is what is usually expected.
        if short_period == 12 and long_period == 26:
            self._short_ema = Ema.with_smoothing(Decimal('0.15'))
            self._long_ema = Ema.with_smoothing(Decimal('0.075'))
        else:
            self._short_ema = Ema(short_period)
            self._long_ema = Ema(long_period)

        self._signal_ema = Ema(signal_period)

        self._t = 0
        self._t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        self._short_ema.update(price)
        self._long_ema.update(price)

        if self._t == self._t1:
            self.value = self._short_ema.value - self._long_ema.value
            self._signal_ema.update(self.value)
            self.signal = self._signal_ema.value
            self.divergence = self.value - self.signal

        self._t = min(self._t + 1, self._t1)
