from decimal import Decimal

from juno import Advice, Candle, indicators
from juno.math import Choice, Int
from juno.modules import get_module_type

from .strategy import Meta, Strategy

_ma_choices = Choice([i.__name__.lower() for i in [
    indicators.Ema,
    indicators.Ema2,
    indicators.Sma,
    indicators.Smma,
    indicators.Dema,
    indicators.Kama,
]])


# Signals a long position when a candle close price goes above moving average and moving average is
# ascending.
# Signals a short position when a candle close price goes below moving average and moving average
# is descending.
class SingleMA(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                'ma': _ma_choices,
                'period': Int(1, 100),
                'persistence': Int(0, 10),
            }
        )

    _ma: indicators.MovingAverage
    _previous_ma_value: Decimal = Decimal('0.0')
    _advice: Advice = Advice.NONE

    def __init__(
        self,
        ma: str = indicators.Ema.__name__.lower(),
        period: int = 50,
        persistence: int = 0,
    ) -> None:
        self._ma = get_module_type(indicators, ma)(period)
        super().__init__(
            maturity=self._ma.maturity, persistence=persistence, ignore_mid_trend=True
        )

    def tick(self, candle: Candle) -> Advice:
        self._ma.update(candle.close)

        if self.mature:
            if candle.close > self._ma.value and self._ma.value > self._previous_ma_value:
                self._advice = Advice.LONG
            elif candle.close < self._ma.value and self._ma.value < self._previous_ma_value:
                self._advice = Advice.SHORT
            else:
                self._advice = Advice.NONE

        self._previous_ma_value = self._ma.value
        return self._advice
