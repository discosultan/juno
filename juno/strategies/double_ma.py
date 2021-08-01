from __future__ import annotations

import operator
from dataclasses import dataclass

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair
from juno.indicators import MA
from juno.utils import get_module_type

from .strategy import Signal, Strategy, ma_choices


@dataclass
class DoubleMAParams:
    short_ma: str = "ema"
    long_ma: str = "ema"
    short_period: int = 5  # Common 5 or 10. Daily.
    long_period: int = 20  # Common 20 or 50.

    def construct(self) -> DoubleMA:
        return DoubleMA(self)


# Signals long when shorter average crosses above the longer.
# Signals short when shorter average crosses below the longer.
# J. Murphy 203
class DoubleMA(Signal):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                "short_ma": ma_choices,
                "long_ma": ma_choices,
                ("short_period", "long_period"): Pair(Int(1, 100), operator.lt, Int(2, 101)),
            }
        )

    _short_ma: MA
    _long_ma: MA
    _advice: Advice = Advice.NONE

    def __init__(self, params: DoubleMAParams) -> None:
        assert params.short_period > 0
        assert params.short_period < params.long_period

        self._short_ma = get_module_type(indicators, params.short_ma)(params.short_period)
        self._long_ma = get_module_type(indicators, params.long_ma)(params.long_period)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return max(self._long_ma.maturity, self._short_ma.maturity)

    @property
    def mature(self) -> bool:
        return self._long_ma.mature and self._short_ma.mature

    def update(self, candle: Candle) -> None:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self._long_ma.mature and self._short_ma.mature:
            if self._short_ma.value >= self._long_ma.value:
                self._advice = Advice.LONG
            elif self._short_ma.value < self._long_ma.value:
                self._advice = Advice.SHORT
