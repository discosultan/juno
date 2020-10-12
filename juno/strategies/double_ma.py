import operator
from decimal import Decimal

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair, Uniform
from juno.indicators import MA, Ema
from juno.utils import get_module_type

from .strategy import Meta, ma_choices


# Signals long when shorter average crosses above the longer.
# Signals short when shorter average crosses below the longer.
# J. Murphy 203
class DoubleMA:
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                'short_ma': ma_choices,
                'long_ma': ma_choices,
                ('short_period', 'long_period'): Pair(Int(1, 100), operator.lt, Int(2, 101)),
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
    def maturity(self) -> int:
        return max(self._long_ma.maturity, self._short_ma.maturity)

    @property
    def mature(self) -> bool:
        return self._long_ma.mature and self._short_ma.mature

    def tick(self, candle: Candle):
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self.mature:
            if self._short_ma.value > self._long_ma.value:
                self._advice = Advice.LONG
            elif self._short_ma.value < self._long_ma.value:
                self._advice = Advice.SHORT


# Moving average moving average crossover.
class DoubleMA2:
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('short_period', 'long_period'): Pair(Int(1, 100), operator.lt, Int(2, 101)),
                'neg_threshold': Uniform(Decimal('-1.000'), Decimal('-0.100')),
                'pos_threshold': Uniform(Decimal('+0.100'), Decimal('+1.000')),
                'short_ma': ma_choices,
                'long_ma': ma_choices,
            }
        )

    _short_ma: MA
    _long_ma: MA
    _neg_threshold: Decimal
    _pos_threshold: Decimal
    _advice: Advice = Advice.NONE

    def __init__(
        self,
        short_period: int,
        long_period: int,
        neg_threshold: Decimal,
        pos_threshold: Decimal,
        short_ma: str = Ema.__name__.lower(),
        long_ma: str = Ema.__name__.lower(),
    ) -> None:
        assert short_period > 0
        assert short_period < long_period

        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)
        self._neg_threshold = neg_threshold
        self._pos_threshold = pos_threshold

    @property
    def maturity(self) -> int:
        return self._long_ma.maturity

    @property
    def mature(self) -> bool:
        return self._long_ma.mature

    @property
    def advice(self) -> Advice:
        return self._advice

    def update(self, candle: Candle) -> Advice:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self.mature:
            diff = (
                100
                * (self._short_ma.value - self._long_ma.value)
                / ((self._short_ma.value + self._long_ma.value) / 2)
            )

            if diff > self._pos_threshold:
                self._advice = Advice.LONG
            elif diff < self._neg_threshold:
                self._advice = Advice.SHORT

        return self._advice
