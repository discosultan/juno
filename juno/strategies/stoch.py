from decimal import Decimal

from juno import Candle, CandleMeta, indicators

from .strategy import Oscillator


class Stoch(Oscillator):
    indicator: indicators.Stoch
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(
        self,
        k_period: int,
        k_sma_period: int,
        d_sma_period: int,
        up_threshold: Decimal = Decimal("80.0"),
        down_threshold: Decimal = Decimal("20.0"),
    ) -> None:
        assert k_period > 0 and k_sma_period > 0 and d_sma_period > 0
        assert up_threshold >= down_threshold

        self.indicator = indicators.Stoch(k_period, k_sma_period, d_sma_period)
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
        return self.indicator.mature and self.indicator.k >= self._up_threshold

    @property
    def oversold(self) -> bool:
        return self.indicator.mature and self.indicator.k < self._down_threshold

    def update(self, candle: Candle, _: CandleMeta) -> None:
        self.indicator.update(candle.high, candle.low, candle.close)
