from decimal import Decimal
from typing import Generic, Type, TypeVar

from .ema import Ema

T = TypeVar('T', float, Decimal)


# Moving Average Convergence Divergence
class Macd(Generic[T]):
    def __init__(self, short_period: int, long_period: int, signal_period: int,  # type: ignore
                 dec: Type[T] = Decimal) -> None:
        if short_period < 1 or long_period < 2 or signal_period < 1:
            raise ValueError(f'Invalid period(s) ({short_period}, {long_period}, {signal_period})')
        if long_period < short_period:
            raise ValueError(
                f'Long period ({long_period}) must be larger '
                f'than or equal to short period ({short_period})'
            )

        self.value: T = dec(0)
        self.signal: T = dec(0)
        self.divergence: T = dec(0)

        # A bit hacky but is what is usually expected.
        self._short_ema: Ema[T]
        self._long_ema: Ema[T]
        if short_period == 12 and long_period == 26:
            self._short_ema = Ema.with_smoothing(dec('0.15'), dec=dec)
            self._long_ema = Ema.with_smoothing(dec('0.075'), dec=dec)
        else:
            self._short_ema = Ema(short_period, dec=dec)
            self._long_ema = Ema(long_period, dec=dec)

        self._signal_ema: Ema[T] = Ema(signal_period, dec=dec)

        self._t = 0
        self._t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: T) -> None:
        self._short_ema.update(price)
        self._long_ema.update(price)

        if self._t == self._t1:
            self.value = self._short_ema.value - self._long_ema.value
            self._signal_ema.update(self.value)
            self.signal = self._signal_ema.value
            self.divergence = self.value - self.signal

        self._t = min(self._t + 1, self._t1)
