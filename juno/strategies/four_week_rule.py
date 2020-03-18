from collections import deque
from decimal import Decimal
from typing import Deque, Generic, Optional, TypeVar

from juno import Advice, Candle, indicators
from juno.math import minmax
from juno.modules import get_module_type

from .strategy import Meta, Strategy

T = TypeVar('T', bound=indicators.MovingAverage)


# Assumes daily candles.
class FourWeekRule(Generic[T], Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
            }
        )

    _prices: Deque[Decimal]
    _ma: T

    def __init__(self, ma: str = indicators.Ema.__name__.lower()) -> None:
        super().__init__(maturity=28)
        self._prices = deque(maxlen=28)
        self._ma = get_module_type(indicators, ma)(14)

    def tick(self, candle: Candle) -> Optional[Advice]:
        self._ma.update(candle.close)
        advice = None

        if self.mature:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                advice = Advice.BUY
            elif candle.close <= self._ma.value:
                advice = Advice.SELL
            if candle.close <= lowest:
                # TODO: Short
                advice = Advice.SELL

        self._prices.append(candle.close)
        return advice
