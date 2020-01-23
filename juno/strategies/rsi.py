from decimal import Decimal
from enum import IntEnum
from typing import Optional

from juno import Advice, Candle, indicators, math

from .strategy import Meta, Strategy


class Status(IntEnum):
    OVERBOUGHT = 0
    OVERSOLD = 1


# TODO: Fix


# Relative Strength Index
class Rsi(Strategy):
    meta = Meta(
        constraints={
            'period': math.Int(1, 101),
            'up_threshold': math.Uniform(Decimal('50.0'), Decimal('100.0')),
            'down_threshold': math.Uniform(Decimal('0.0'), Decimal('50.0')),
            'persistence': math.Int(0, 10),
        }
    )

    def __init__(
        self,
        period: int,  # 14
        up_threshold: Decimal,
        down_threshold: Decimal,
        persistence: int
    ) -> None:
        super().__init__(maturity=period - 1, persistence=persistence)
        self.validate(period, up_threshold, down_threshold, persistence)
        self._rsi = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold
        self._prev_status: Optional[Status] = None

    def tick(self, candle: Candle) -> Optional[Advice]:
        self._rsi.update(candle.close)

        advice = None
        if self.mature:
            status = None
            if self._rsi.value < self._down_threshold:
                status = Status.OVERSOLD
            elif self._rsi.value > self._up_threshold:
                status = Status.OVERBOUGHT

            if status is None and self._prev_status is Status.OVERBOUGHT:
                advice = Advice.SELL
            elif status is None and self._prev_status is Status.OVERSOLD:
                advice = Advice.BUY

            self._prev_status = status

        return advice
