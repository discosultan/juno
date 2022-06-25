import operator

from juno import Advice, Candle, CandleMeta, indicators
from juno.constraints import Int, Pair

from .strategy import Signal, Strategy


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

    def __init__(
        self,
        short_period: int = 12,
        long_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        self._macd = indicators.Macd(short_period, long_period, signal_period)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._macd.maturity

    @property
    def mature(self) -> bool:
        return self._macd.mature

    def update(self, candle: Candle, _: CandleMeta) -> None:
        self._macd.update(candle.close)

        if self._macd.mature:
            if self._macd.value > self._macd.signal:
                self._advice = Advice.LONG
            else:
                self._advice = Advice.SHORT
