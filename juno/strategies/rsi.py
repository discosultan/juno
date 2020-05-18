from decimal import Decimal

from juno import Advice, Candle, indicators, math

from .strategy import Meta, Strategy


# RSI based strategy which signals buy when the indicator is coming out of an oversold area and
# sell when coming out of an overbought area.
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
    _advice: Advice = Advice.NONE
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(
        self,
        period: int = 14,
        up_threshold: Decimal = Decimal('70.0'),
        down_threshold: Decimal = Decimal('30.0'),
        persistence: int = 0,
    ) -> None:
        super().__init__(maturity=period - 1, persistence=persistence)
        self.validate(period, up_threshold, down_threshold, persistence)
        self._rsi = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold

    def tick(self, candle: Candle) -> Advice:
        self._rsi.update(candle.close)

        if self.mature:
            if (
                self._previous_rsi_value <= self._down_threshold
                and self._rsi.value > self._down_threshold
            ):
                self._advice = Advice.LONG
            elif (
                self._previous_rsi_value >= self._up_threshold
                and self._rsi.value < self._up_threshold
            ):
                self._advice = Advice.SHORT

        self._previous_rsi_value = self._rsi.value
        return self._advice
