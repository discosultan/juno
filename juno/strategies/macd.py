import operator

from juno import Advice, Candle, Trend, indicators, math
from juno.utils import Persistence

from .strategy import Meta, Strategy


# Moving Average Convergence Divergence.
class Macd(Strategy):
    meta = Meta(
        constraints={
            ('short_period', 'long_period'):
                math.Pair(math.Int(1, 51), operator.lt, math.Int(2, 101)),
            'signal_period': math.Int(1, 101),
            'persistence': math.Int(0, 10),
        }
    )

    def __init__(
        self,
        short_period: int,  # 12
        long_period: int,  # 26
        signal_period: int,  # 9
        persistence: int
    ) -> None:
        self.validate(short_period, long_period, signal_period, persistence)
        self._macd = indicators.Macd(short_period, long_period, signal_period)
        self._persistence = Persistence(level=persistence, allow_initial_trend=False)
        self._t = 0
        self._t1 = max(long_period, signal_period) - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, candle: Candle) -> Advice:
        self._macd.update(candle.close)

        trend = Trend.UNKNOWN
        if self._t == self._t1:
            if self._macd.value > self._macd.signal:
                trend = Trend.UP
            else:
                trend = Trend.DOWN

        self._t = min(self._t + 1, self._t1)

        return Strategy.advice(*self._persistence.update(trend))
