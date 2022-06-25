from __future__ import annotations

import operator
from dataclasses import dataclass

from juno import Advice, Candle, CandleMeta, indicators
from juno.constraints import Int, Pair
from juno.indicators import MA, Ema
from juno.typing import Constructor
from juno.utils import get_module_type

from .strategy import Signal, Strategy, ma_choices


@dataclass
class DoubleMAParams(Constructor):
    short_ma: str = "ema"
    long_ma: str = "ema"
    short_period: int = 5  # Common 5 or 10. Daily.
    long_period: int = 20  # Common 20 or 50.

    def construct(self) -> DoubleMA:
        return DoubleMA(
            short_ma=self.short_ma,
            long_ma=self.long_ma,
            short_period=self.short_period,
            long_period=self.long_period,
        )


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

    def __init__(
        self,
        short_ma: str = Ema.__name__.lower(),
        long_ma: str = Ema.__name__.lower(),
        short_period: int = 5,  # Common 5 or 10. Daily.
        long_period: int = 20,  # Common 20 or 50.
    ) -> None:
        assert short_period > 0
        assert short_period < long_period

        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return max(self._long_ma.maturity, self._short_ma.maturity)

    @property
    def mature(self) -> bool:
        return self._long_ma.mature and self._short_ma.mature

    def update(self, candle: Candle, _: CandleMeta) -> None:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self._long_ma.mature and self._short_ma.mature:
            if self._short_ma.value >= self._long_ma.value:
                self._advice = Advice.LONG
            elif self._short_ma.value < self._long_ma.value:
                self._advice = Advice.SHORT
