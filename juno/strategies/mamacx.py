import operator
from decimal import Decimal
from enum import IntEnum
from typing import Any, Optional

from juno import Advice, Candle, indicators, math
from juno.modules import get_module_type

from .strategy import Meta, Strategy


class MA(IntEnum):
    EMA = 0
    EMA2 = 1
    SMA = 2
    SMMA = 3
    DEMA = 4


_ma_choices = math.Choice([MA.EMA, MA.EMA2, MA.SMA, MA.SMMA, MA.DEMA])


# Moving average moving average crossover.
class MAMACX(Strategy):
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

    _short_ma: Any  # TODO: FIX!!
    _long_ma: Any
    _neg_threshold: Decimal
    _pos_threshold: Decimal

    def __init__(
        self,
        short_period: int,
        long_period: int,
        neg_threshold: Decimal,
        pos_threshold: Decimal,
        persistence: int,
        short_ma: MA = MA.EMA,
        long_ma: MA = MA.EMA
    ) -> None:
        super().__init__(maturity=long_period - 1, persistence=persistence)
        self.validate(
            short_period, long_period, neg_threshold, pos_threshold, persistence, short_ma, long_ma
        )

        self._short_ma = get_module_type(indicators, short_ma.name.lower())(short_period)
        self._long_ma = get_module_type(indicators, long_ma.name.lower())(long_period)
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
                return Advice.BUY
            elif diff < self._neg_threshold:
                return Advice.SELL

        return None
