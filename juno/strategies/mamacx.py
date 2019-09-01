import operator
from decimal import Decimal

from juno import Advice, Candle, Trend, math
from juno.indicators import get_indicator_type
from juno.utils import Persistence

from .strategy import Strategy


# Moving average moving average crossover.
class MAMACX(Strategy):
    def __init__(
        self, short_period: int, long_period: int, neg_threshold: Decimal, pos_threshold: Decimal,
        persistence: int, short_ma: str = 'ema', long_ma: str = 'ema'
    ) -> None:
        self.validate(
            short_period, long_period, neg_threshold, pos_threshold, persistence, short_ma, long_ma
        )
        self._ma_short = get_indicator_type(short_ma)(short_period)
        self._ma_long = get_indicator_type(long_ma)(long_period)
        self._neg_threshold = neg_threshold
        self._pos_threshold = pos_threshold
        self._persistence = Persistence(level=persistence, allow_initial_trend=False)
        self._t = 0
        self._t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    @staticmethod
    def meta():
        # ma_choices = ['sma', 'smma', 'ema', 'ema2']
        return {
            ('short_period', 'long_period'): math.IntPair(1, 51, operator.lt, 2, 101),
            'neg_threshold': math.Uniform(Decimal('-1.000'), Decimal('-0.100')),
            'pos_threshold': math.Uniform(Decimal('+0.100'), Decimal('+1.000')),
            'persistence': math.Int(0, 10),
            # 'short_ma': math.Choice(ma_choices),
            # 'long_ma': math.Choice(ma_choices),
        }

    def update(self, candle: Candle) -> Advice:
        self._ma_short.update(candle.close)
        self._ma_long.update(candle.close)

        trend = Trend.UNKNOWN
        if self._t == self._t1:
            diff = 100 * (self._ma_short.value - self._ma_long.value
                          ) / ((self._ma_short.value + self._ma_long.value) / 2)

            if diff > self._pos_threshold:
                trend = Trend.UP
            elif diff < self._neg_threshold:
                trend = Trend.DOWN

        self._t = min(self._t + 1, self._t1)

        return Strategy.advice(*self._persistence.update(trend))
