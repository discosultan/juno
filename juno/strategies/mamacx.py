import operator
from decimal import Decimal

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair, Uniform
from juno.indicators import MA, Ema
from juno.utils import get_module_type

from .strategy import Meta, MidTrendPolicy, Strategy, ma_choices


# Moving average moving average crossover.
class MAMACX(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('short_period', 'long_period'): Pair(Int(1, 100), operator.lt, Int(2, 101)),
                'neg_threshold': Uniform(Decimal('-1.000'), Decimal('-0.100')),
                'pos_threshold': Uniform(Decimal('+0.100'), Decimal('+1.000')),
                'persistence': Int(0, 10),
                'short_ma': ma_choices,
                'long_ma': ma_choices,
            }
        )

    _short_ma: MA
    _long_ma: MA
    _neg_threshold: Decimal
    _pos_threshold: Decimal

    def __init__(
        self,
        short_period: int,
        long_period: int,
        neg_threshold: Decimal,
        pos_threshold: Decimal,
        persistence: int = 0,
        short_ma: str = Ema.__name__.lower(),
        long_ma: str = Ema.__name__.lower(),
    ) -> None:
        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)

        super().__init__(
            maturity=max(self._long_ma.maturity, self._short_ma.maturity),
            persistence=persistence,
            mid_trend_policy=MidTrendPolicy.IGNORE,
        )
        self.validate(
            short_period, long_period, neg_threshold, pos_threshold, persistence, short_ma, long_ma
        )

        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)
        self._neg_threshold = neg_threshold
        self._pos_threshold = pos_threshold

    def tick(self, candle: Candle) -> Advice:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self.mature:
            diff = (
                100
                * (self._short_ma.value - self._long_ma.value)
                / ((self._short_ma.value + self._long_ma.value) / 2)
            )

            if diff > self._pos_threshold:
                return Advice.LONG
            elif diff < self._neg_threshold:
                return Advice.SHORT

        return Advice.NONE
