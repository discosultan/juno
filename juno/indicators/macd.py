from decimal import Decimal
from typing import Tuple

from .ema import Ema


# Moving Average Convergence Divergence
class Macd:
    value: Decimal = Decimal('0.0')
    signal: Decimal = Decimal('0.0')
    histogram: Decimal = Decimal('0.0')

    _short_ema: Ema
    _long_ema: Ema
    _signal_ema: Ema

    def __init__(self, short_period: int, long_period: int, signal_period: int) -> None:
        if short_period < 1 or long_period < 2 or signal_period < 1:
            raise ValueError(f'Invalid period(s) ({short_period}, {long_period}, {signal_period})')
        if long_period < short_period:
            raise ValueError(
                f'Long period ({long_period}) must be larger than or equal to short period '
                f'({short_period})'
            )

        # A bit hacky but is what is usually expected.
        if short_period == 12 and long_period == 26:
            self._short_ema = Ema.with_smoothing(short_period, Decimal('0.15'))
            self._long_ema = Ema.with_smoothing(long_period, Decimal('0.075'))
        else:
            self._short_ema = Ema(short_period)
            self._long_ema = Ema(long_period)
        self._signal_ema = Ema(signal_period)

    @property
    def maturity(self) -> int:
        return (
            max(self._long_ema.maturity, self._short_ema.maturity)
            + self._signal_ema.maturity
            - 1
        )

    @property
    def mature(self) -> bool:
        return self._signal_ema.mature

    def update(self, price: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
        self._short_ema.update(price)
        self._long_ema.update(price)

        if self._long_ema.mature and self._short_ema.mature:
            self.value = self._short_ema.value - self._long_ema.value
            self.signal = self._signal_ema.update(self.value)
            self.histogram = self.value - self.signal

        return self.value, self.signal, self.histogram
