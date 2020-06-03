import operator

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair

from .strategy import Meta, Strategy


# Simple MACD based strategy which signals buy when MACD value above the signal line and sell if
# below.
class Macd(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('short_period', 'long_period'): Pair(Int(1, 100), operator.lt, Int(2, 101)),
                'signal_period': Int(1, 101),
                'persistence': Int(0, 10),
            }
        )

    _macd: indicators.Macd

    def __init__(
        self,
        short_period: int = 12,
        long_period: int = 26,
        signal_period: int = 9,
        persistence: int = 0,
    ) -> None:
        super().__init__(maturity=max(long_period, signal_period) - 1, persistence=persistence)
        self.validate(short_period, long_period, signal_period, persistence)

        self._macd = indicators.Macd(short_period, long_period, signal_period)

    def tick(self, candle: Candle) -> Advice:
        self._macd.update(candle.close)

        if self.mature:
            if self._macd.value > self._macd.signal:
                return Advice.LONG
            else:
                return Advice.SHORT

        return Advice.NONE
