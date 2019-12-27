import operator
from decimal import Decimal

from juno import Advice, Candle, Trend, indicators, math
from juno.utils import Persistence, get_module_type

from .strategy import Meta, Strategy

_ma_choices = math.Choice(['sma', 'smma', 'ema', 'ema2'])


# Moving average moving average crossover.
class MAMACX(Strategy):
    meta = Meta(
        constraints={
            ('short_period', 'long_period'):
                math.Pair(math.Int(1, 51), operator.lt, math.Int(2, 101)),
            'neg_threshold':
                math.Uniform(Decimal('-1.000'), Decimal('-0.100')),
            'pos_threshold':
                math.Uniform(Decimal('+0.100'), Decimal('+1.000')),
            'persistence':
                math.Int(0, 10),
            'short_ma':
                _ma_choices,
            'long_ma':
                _ma_choices,
        },
        identifier='{short_ma}{long_ma}cx'
    )

    def __init__(
        self,
        short_period: int,
        long_period: int,
        neg_threshold: Decimal,
        pos_threshold: Decimal,
        persistence: int,
        short_ma: str = 'ema',
        long_ma: str = 'ema'
    ) -> None:
        self.validate(
            short_period, long_period, neg_threshold, pos_threshold, persistence, short_ma, long_ma
        )
        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)
        self._neg_threshold = neg_threshold
        self._pos_threshold = pos_threshold
        self._persistence = Persistence(level=persistence, allow_initial_trend=False)
        self._t = 0
        self._t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, candle: Candle) -> Advice:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        trend = Trend.UNKNOWN
        if self._t == self._t1:
            diff = 100 * (self._short_ma.value -
                          self._long_ma.value) / ((self._short_ma.value + self._long_ma.value) / 2)

            if diff > self._pos_threshold:
                trend = Trend.UP
            elif diff < self._neg_threshold:
                trend = Trend.DOWN

        self._t = min(self._t + 1, self._t1)

        return Strategy.advice(*self._persistence.update(trend))
