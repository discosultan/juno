import operator
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from juno import Advice, Candle, indicators, math
from juno.modules import get_module_type

from .strategy import Meta, Strategy

_ma_choices = math.Choice([i.__name__.lower() for i in [
    indicators.Ema,
    indicators.Ema2,
    indicators.Sma,
    indicators.Smma,
    indicators.Dema,
    indicators.Kama,
]])


TShort = TypeVar('TShort', bound=indicators.MovingAverage)
TLong = TypeVar('TLong', bound=indicators.MovingAverage)


# Moving average moving average crossover.
class MAMACX(Generic[TShort, TLong], Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('short_period', 'long_period'):
                    math.Pair(math.Int(1, 100), operator.lt, math.Int(2, 101)),
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
            }
        )

    _short_ma: TShort
    _long_ma: TLong
    _neg_threshold: Decimal
    _pos_threshold: Decimal

    def __init__(
        self,
        short_period: int,
        long_period: int,
        neg_threshold: Decimal,
        pos_threshold: Decimal,
        persistence: int = 0,
        short_ma: str = indicators.Ema.__name__.lower(),
        long_ma: str = indicators.Ema.__name__.lower(),
    ) -> None:
        super().__init__(maturity=long_period - 1, persistence=persistence)
        self.validate(
            short_period, long_period, neg_threshold, pos_threshold, persistence, short_ma, long_ma
        )

        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)
        self._neg_threshold = neg_threshold
        self._pos_threshold = pos_threshold

    def tick(self, candle: Candle) -> Optional[Advice]:
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

        return None
