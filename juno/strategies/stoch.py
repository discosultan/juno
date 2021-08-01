from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from juno import Candle, indicators

from .strategy import Oscillator


@dataclass
class StochParams:
    k_period: int
    k_sma_period: int
    d_sma_period: int
    up_threshold: Decimal = Decimal("80.0")
    down_threshold: Decimal = Decimal("20.0")

    def construct(self) -> Stoch:
        return Stoch(self)


class Stoch(Oscillator):
    indicator: indicators.Stoch
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(self, params: StochParams) -> None:
        assert params.k_period > 0 and params.k_sma_period > 0 and params.d_sma_period > 0
        assert params.up_threshold >= params.down_threshold

        self.indicator = indicators.Stoch(
            params.k_period, params.k_sma_period, params.d_sma_period
        )
        self._up_threshold = params.up_threshold
        self._down_threshold = params.down_threshold

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

    def update(self, candle: Candle) -> None:
        self.indicator.update(candle.high, candle.low, candle.close)
