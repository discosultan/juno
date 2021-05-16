from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from juno import Advice, indicators
from juno.candles import Candle
from juno.constraints import Int
from juno.indicators import MA, Ema2
from juno.utils import get_module_type

from .strategy import Signal, Strategy, ma_choices


@dataclass
class SingleMAParams:
    ma: str = 'ema'
    period: int = 50

    def construct(self) -> SingleMA:
        return SingleMA(
            period=self.period,
            ma=self.ma,
        )


# Signals long when a candle close price goes above moving average and moving average is ascending.
# Signals short when a candle close price goes below moving average and moving average is
# descending.
# J. Murphy 201
class SingleMA(Signal):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                'ma': ma_choices,
                'period': Int(1, 100),
            }
        )

    _ma: MA
    _previous_ma_value: Decimal = Decimal('0.0')
    _advice: Advice = Advice.NONE
    _t: int = 0
    _t1: int

    def __init__(
        self,
        ma: str = Ema2.__name__.lower(),
        period: int = 50,  # Daily.
    ) -> None:
        self._ma = get_module_type(indicators, ma)(period)
        self._t1 = self._ma.maturity + 1

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, candle: Candle) -> None:
        self._t = min(self._t + 1, self._t1)

        self._ma.update(candle.close)

        if self._t >= self._t1:
            if candle.close > self._ma.value and self._ma.value > self._previous_ma_value:
                self._advice = Advice.LONG
            elif candle.close < self._ma.value and self._ma.value < self._previous_ma_value:
                self._advice = Advice.SHORT

        self._previous_ma_value = self._ma.value
