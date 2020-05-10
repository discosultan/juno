from collections import deque
from decimal import Decimal
from typing import Deque

from juno import Advice, Candle, indicators
from juno.math import Choice, Int, minmax
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


# Signals a long position when a candle close price goes above a highest four week close price.
# Signals a short position when a candle close price goes below a lowest four week close price.
# Signals liquidation when a candle close price crosses a two week moving average.
# Works with daily candles!
class FourWeekRule(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                'period': Int(2, 100),
                'ma': _ma_choices,
            }
        )

    _prices: Deque[Decimal]
    _ma: indicators.MovingAverage
    _advice: Advice = Advice.NONE

    def __init__(self, period: int = 28, ma: str = indicators.Sma.__name__.lower()) -> None:
        super().__init__(maturity=period, persistence=0, ignore_mid_trend=False)
        self._prices = deque(maxlen=period)
        self._ma = get_module_type(indicators, ma)(period // 2)

    def tick(self, candle: Candle) -> Advice:
        self._ma.update(candle.close)

        if self.mature:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                self._advice = Advice.LONG
            elif candle.close <= lowest:
                self._advice = Advice.SHORT
            elif (
                (self._advice is Advice.LONG and candle.close <= self._ma.value)
                or (self._advice is Advice.SHORT and candle.close >= self._ma.value)
            ):
                self._advice = Advice.LIQUIDATE

        self._prices.append(candle.close)
        return self._advice
