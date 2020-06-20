import operator

from juno import Advice, Candle, indicators
from juno.constraints import Int, Pair
from juno.indicators import MA, Ema
from juno.utils import get_module_type

from .strategy import Meta, MidTrendPolicy, Strategy, ma_choices


# Signals long when shorter average crosses above the longer.
# Signals short when shorter average crosses below the longer.
# J. Murphy 203
class DoubleMA(Strategy):
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
        short_period: int = 5,  # Daily. Common 5 or 10.
        long_period: int = 20,  # Common 20 or 50.
    ) -> None:
        assert short_period < long_period
        self._short_ma = get_module_type(indicators, short_ma)(short_period)
        self._long_ma = get_module_type(indicators, long_ma)(long_period)
        super().__init__(
            maturity=long_period,
            persistence=0,
            mid_trend_policy=MidTrendPolicy.IGNORE,
        )

    def tick(self, candle: Candle) -> Advice:
        self._short_ma.update(candle.close)
        self._long_ma.update(candle.close)

        if self.mature:
            if self._short_ma.value > self._long_ma.value:
                self._advice = Advice.LONG
            elif self._short_ma.value < self._long_ma.value:
                self._advice = Advice.SHORT

        return self._advice
