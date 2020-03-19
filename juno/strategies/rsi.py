from decimal import Decimal
from typing import Optional

from juno import Advice, Candle, indicators, math

from .strategy import Meta, Strategy


# Simple RSI based strategy which signals buy when oversold and sell when overbought. Ineffective
# on its own but can be useful when combining with other strategies.
class Rsi(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                'period': math.Int(1, 101),
                'up_threshold': math.Uniform(Decimal('50.0'), Decimal('100.0')),
                'down_threshold': math.Uniform(Decimal('0.0'), Decimal('50.0')),
                'persistence': math.Int(0, 10),
            }
        )

    _rsi: indicators.Rsi
    _previous_rsi_value: Decimal
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(
        self,
        period: int = 14,
        up_threshold: Decimal = Decimal('75.0'),
        down_threshold: Decimal = Decimal('25.0'),
        persistence: int = 0,
    ) -> None:
        super().__init__(maturity=period - 1, persistence=persistence)
        self.validate(period, up_threshold, down_threshold, persistence)
        self._rsi = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold

    def tick(self, candle: Candle) -> Optional[Advice]:
        self._rsi.update(candle.close)

        advice = None
        if self.mature:
            if (
                self._previous_rsi_value <= self._down_threshold
                and self._rsi.value > self._down_threshold
            ):
                advice = Advice.BUY
            elif (
                self._previous_rsi_value >= self._up_threshold
                and self._rsi.value < self._up_threshold
            ):
                advice = Advice.SELL

        self._previous_rsi_value = self._rsi.value
        return advice
