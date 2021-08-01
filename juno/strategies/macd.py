from __future__ import annotations

import operator
from dataclasses import dataclass

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair

from .strategy import Signal, Strategy


@dataclass
class MacdParams:
    short_period: int = 12
    long_period: int = 26
    signal_period: int = 9

    def construct(self) -> Macd:
        return Macd(self)


# Simple MACD based strategy which signals buy when MACD value above the signal line and sell if
# below.
class Macd(Signal):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                ("short_period", "long_period"): Pair(Int(1, 100), operator.lt, Int(2, 101)),
                "signal_period": Int(1, 101),
                "persistence": Int(0, 10),
            }
        )

    _macd: indicators.Macd
    _advice: Advice = Advice.NONE

    def __init__(self, params: MacdParams) -> None:
        self._macd = indicators.Macd(params.short_period, params.long_period, params.signal_period)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._macd.maturity

    @property
    def mature(self) -> bool:
        return self._macd.mature

    def update(self, candle: Candle) -> None:
        self._macd.update(candle.close)

        if self._macd.mature:
            if self._macd.value > self._macd.signal:
                self._advice = Advice.LONG
            else:
                self._advice = Advice.SHORT
