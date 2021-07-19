from decimal import Decimal

from .ema import Ema


# Klinger Volume Oscillator
class Kvo:
    value: Decimal = Decimal("0.0")
    _short_ema: Ema
    _long_ema: Ema
    _prev_hlc: Decimal = Decimal("0.0")
    _prev_dm: Decimal = Decimal("0.0")
    _cm: Decimal = Decimal("0.0")
    _trend: int = 0
    _t: int = 0
    _t1: int = 2

    def __init__(self, short_period: int, long_period: int) -> None:
        if short_period < 1:
            raise ValueError(f"Invalid short period ({short_period})")
        if long_period < short_period:
            raise ValueError(
                f"Long period ({long_period}) cannot be shorter than short period ({short_period})"
            )

        self._short_ema = Ema(short_period)
        self._long_ema = Ema(long_period)

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal, volume: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        hlc = high + low + close
        dm = high - low

        if self._t > 1:
            if hlc > self._prev_hlc and self._trend != 1:
                self._trend = 1
                self._cm = self._prev_dm
            elif hlc < self._prev_hlc and self._trend != -1:
                self._trend = -1
                self._cm = self._prev_dm
            self._cm += dm

            vf = volume * abs(dm / self._cm * 2 - 1) * 100 * self._trend

            self._short_ema.update(vf)
            self._long_ema.update(vf)

            self.value = self._short_ema.value - self._long_ema.value

        self._prev_dm = dm
        self._prev_hlc = hlc
        return self.value
