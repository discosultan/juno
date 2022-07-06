import operator
from decimal import Decimal

from juno import Advice, Candle, CandleMeta, indicators
from juno.constraints import Int, Pair, Uniform
from juno.indicators import MA, Ema
from juno.inspect import get_module_type

from .strategy import Signal, Strategy, ma_choices


# Moving average moving average crossover.
class DoubleMA2(Signal):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                ("short_period", "long_period"): Pair(Int(1, 100), operator.lt, Int(2, 101)),
                "neg_threshold": Uniform(Decimal("-1.000"), Decimal("-0.100")),
                "pos_threshold": Uniform(Decimal("+0.100"), Decimal("+1.000")),
                "short_ma": ma_choices,
                "long_ma": ma_choices,
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
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._long_ma.maturity

    @property
    def mature(self) -> bool:
        return self._long_ma.mature

    def update(self, candle: Candle, _: CandleMeta) -> None:
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
