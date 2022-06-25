from decimal import Decimal

from juno import Candle, CandleMeta, indicators
from juno.constraints import Int, Uniform

from .strategy import Oscillator, Strategy


# TODO: For example, well-known market technician Constance Brown, CMT, has promoted the idea that
# an oversold reading on the RSI in an uptrend is likely much higher than 30%, and an overbought
# reading on the RSI during a downtrend is much lower than the 70% level.
class Rsi(Oscillator):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                "period": Int(1, 101),
                "up_threshold": Uniform(Decimal("50.0"), Decimal("100.0")),
                "down_threshold": Uniform(Decimal("0.0"), Decimal("50.0")),
            }
        )

    indicator: indicators.Rsi
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(
        self,
        period: int = 14,
        up_threshold: Decimal = Decimal("70.0"),
        down_threshold: Decimal = Decimal("30.0"),
    ) -> None:
        assert period > 0
        assert up_threshold >= down_threshold

        self.indicator = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold

    @property
    def maturity(self) -> int:
        return self.indicator.maturity

    @property
    def mature(self) -> bool:
        return self.indicator.mature

    @property
    def overbought(self) -> bool:
        return self.indicator.mature and self.indicator.value >= self._up_threshold

    @property
    def oversold(self) -> bool:
        return self.indicator.mature and self.indicator.value < self._down_threshold

    def update(self, candle: Candle, _: CandleMeta) -> None:
        self.indicator.update(candle.close)
