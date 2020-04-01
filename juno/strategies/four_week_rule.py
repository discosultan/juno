from collections import deque
from decimal import Decimal
from typing import Deque, Generic, TypeVar

from juno import Advice, Candle, indicators
from juno.math import minmax
from juno.modules import get_module_type

from .strategy import Meta, Strategy

T = TypeVar('T', bound=indicators.MovingAverage)


# Signals a long position when a candle close price goes above a highest four week close price.
# Signals a short position when a candle close price goes below a lowest four week close price.
# Signals liquidation when a candle close price crosses a two week moving average.
# Works with daily candles!
class FourWeekRule(Generic[T], Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
            }
        )

    _prices: Deque[Decimal]
    _ma: T
    _advice: Advice = Advice.LIQUIDATE

    def __init__(self, ma: str = indicators.Ema.__name__.lower()) -> None:
        super().__init__(maturity=28)
        self._prices = deque(maxlen=28)
        self._ma = get_module_type(indicators, ma)(14)

    def tick(self, candle: Candle) -> Advice:
        self._ma.update(candle.close)

        if self.mature:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                self._advice = Advice.LONG
            elif candle.close <= lowest:
                self._advice = Advice.SHORT
            elif self._advice is Advice.LONG and candle.close <= self._ma.value:
                self._advice = Advice.LIQUIDATE
            elif self._advice is Advice.SHORT and candle.close >= self._ma.value:
                self._advice = Advice.LIQUIDATE

        self._prices.append(candle.close)
        return self._advice
