from decimal import Decimal
from typing import Literal

from .ema import Ema
from .sma import Sma
from .smma import Smma
from .wma import Wma

_MA = Ema | Sma | Smma | Wma
_MA_Type = Literal["ema", "rma", "sma", "wma"]


class Atr2:
    value: Decimal = Decimal("0.0")

    _ma: _MA
    _t: int = 0
    _t1: int
    _t2: int
    _sum: Decimal = Decimal("0.0")
    _prev_close: Decimal

    def __init__(self, period: int, ma: _MA_Type = "sma") -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

        self._ma = _get_ma(period, ma)
        self._t1 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        if self._t >= 2:
            tr = _calc_truerange(high, low, self._prev_close)
            self._ma.update(tr)

        if self._t >= self._t1:
            self.value = self._ma.value

        self._prev_close = close
        return self.value


def _calc_truerange(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _get_ma(period: int, ma: _MA_Type) -> _MA:
    if ma == "ema":
        return Ema(period)
    elif ma == "rma":
        # return Ema.with_smoothing(period, Decimal("1.0") / period)
        return Smma(period)
    elif ma == "sma":
        return Sma(period)
    elif ma == "wma":
        return Wma(period)
    else:
        raise NotImplementedError()
