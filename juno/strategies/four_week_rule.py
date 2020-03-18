from collections import deque
from decimal import Decimal
from typing import Deque, Optional

from juno import Advice, Candle
from juno.indicators import Sma
from juno.math import minmax

from .strategy import Meta, Strategy


# Assumes daily candles.
class FourWeekRule(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
            }
        )

    _prices: Deque[Decimal]
    _sma: Sma

    def __init__(self) -> None:
        super().__init__(maturity=28)
        self._prices = deque(maxlen=28)
        self._sma = Sma(14)

    def tick(self, candle: Candle) -> Optional[Advice]:
        self._sma.update(candle.close)
        advice = None

        if self.mature:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                advice = Advice.BUY
            elif candle.close <= self._sma.value:
                advice = Advice.SELL
            if candle.close <= lowest:
                # TODO: Short
                advice = Advice.SELL

        self._prices.append(candle.close)
        return advice
