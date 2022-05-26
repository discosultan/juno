from collections import deque
from decimal import Decimal

from .atr import Atr


class ChandelierExit:
    long: Decimal = Decimal("0.0")
    short: Decimal = Decimal("0.0")

    _atr: Atr
    _highs: deque[Decimal]
    _lows: deque[Decimal]
    _t: int = 0
    _t1: int

    def __init__(
        self,
        long_period: int = 22,
        short_period: int = 22,
        atr_period: int = 22,
    ) -> None:
        if long_period < 1:
            raise ValueError(f"Invalid long period ({long_period})")
        if short_period < 1:
            raise ValueError(f"Invalid short period ({short_period})")

        self._atr = Atr(period=atr_period)
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
        self._highs.append(high)
        self._lows.append(low)

        if self.mature:
            triple_atr = self._atr.value * 3
            self.long = max(self._highs) - triple_atr
            self.short = max(self._lows) + triple_atr

        return self.long, self.short
