from collections import deque
from decimal import Decimal

from .atr2 import Atr2 as Atr


# Ref: https://www.tradingview.com/script/AqXxNS7j-Chandelier-Exit/
class ChandelierExit:
    long: Decimal = Decimal("0.0")
    short: Decimal = Decimal("0.0")

    _prev_long: Decimal = Decimal("0.0")
    _prev_short: Decimal = Decimal("0.0")
    _prev_close: Decimal = Decimal("0.0")

    _atr: Atr
    _atr_multiplier: int
    _use_close: bool
    _highs: deque[Decimal]
    _lows: deque[Decimal]
    _t: int = 0
    _t1: int

    def __init__(
        self,
        long_period: int = 22,
        short_period: int = 22,
        atr_period: int = 22,
        atr_multiplier: int = 3,
        use_close: bool = False,
    ) -> None:
        if long_period < 1:
            raise ValueError(f"Invalid long period ({long_period})")
        if short_period < 1:
            raise ValueError(f"Invalid short period ({short_period})")

        self._atr = Atr(period=atr_period)
        self._atr_multiplier = atr_multiplier
        self._use_close = use_close
        self._highs = deque(maxlen=long_period)
        self._lows = deque(maxlen=short_period)
        self._t1 = max(long_period, short_period)

    @property
    def maturity(self) -> int:
        return max(self._atr.maturity, self._t1)

    @property
    def mature(self) -> bool:
        return self._t >= self._t1 and self._atr.mature

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> tuple[Decimal, Decimal]:
        self._t = min(self._t + 1, self._t1)

        self._atr.update(high=high, low=low, close=close)
        self._highs.append(close if self._use_close else high)
        self._lows.append(close if self._use_close else low)

        if self.mature:
            multiplied_atr = self._atr.value * self._atr_multiplier
            self.long = max(self._highs) - multiplied_atr
            self.short = min(self._lows) + multiplied_atr

            if self._prev_long == 0:
                self._prev_long = self.long
            if self._prev_short == 0:
                self._prev_short = self.short

            self.long = (
                max(self.long, self._prev_long)
                if self._prev_close > self._prev_long
                else self.long
            )
            self.short = (
                min(self.short, self._prev_short)
                if self._prev_close < self._prev_short
                else self.short
            )

            self._prev_long = self.long
            self._prev_short = self.short

        self._prev_close = close

        return self.long, self.short
