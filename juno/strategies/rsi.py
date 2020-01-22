from decimal import Decimal
from enum import IntEnum
from typing import Optional

from juno import Advice, Candle, Trend, indicators, math
from juno.utils import Persistence

from .strategy import Meta, Strategy


class Status(IntEnum):
    OVERBOUGHT = 0
    OVERSOLD = 1


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
        self.validate(period, up_threshold, down_threshold, persistence)
        self._rsi = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold
        self._persistence = Persistence(level=persistence, allow_initial_trend=False)
        self._prev_status: Optional[Status] = None
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, candle: Candle) -> Advice:
        self._rsi.update(candle.close)

        trend = Trend.UNKNOWN
        if self._t == self._t1:
            status = None
            if self._rsi.value < self._down_threshold:
                status = Status.OVERSOLD
            elif self._rsi.value > self._up_threshold:
                status = Status.OVERBOUGHT

            if status is None and self._prev_status is Status.OVERBOUGHT:
                trend = Trend.DOWN
            elif status is None and self._prev_status is Status.OVERSOLD:
                trend = Trend.UP

            self._prev_status = status

        self._t = min(self._t + 1, self._t1)

        return Strategy.advice(*self._persistence.update(trend))
