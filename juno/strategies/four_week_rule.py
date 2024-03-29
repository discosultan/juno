from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from juno import Advice, Candle, CandleMeta, indicators
from juno.constraints import Int
from juno.indicators import MA
from juno.inspect import Constructor, get_module_type
from juno.math import minmax

from .strategy import Signal, Strategy, ma_choices


@dataclass
class FourWeekRuleParams(Constructor):
    period: int = 28
    ma: str = "ema"
    ma_period: int = 14  # Normally half the period.

    def construct(self) -> FourWeekRule:
        return FourWeekRule(
            period=self.period,
            ma=self.ma,
            ma_period=self.ma_period,
        )


# Signals a long position when a candle close price goes above a highest four week close price.
# Signals a short position when a candle close price goes below a lowest four week close price.
# Signals liquidation when a candle close price crosses a two week moving average.
# Works with daily candles!
class FourWeekRule(Signal):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                "period": Int(2, 100),
                "ma": ma_choices,
                "ma_period": Int(2, 100),
            }
        )

    _prices: deque[Decimal]
    _ma: MA
    _advice: Advice = Advice.NONE
    _t: int = 0
    _t1: int

    def __init__(
        self,
        period: int = 28,
        ma: str = "ema",
        ma_period: int = 14,  # Normally half the period.
    ) -> None:
        self._prices = deque(maxlen=period)
        self._ma = get_module_type(indicators, ma)(ma_period)
        self._t1 = period + 1

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, candle: Candle, _: CandleMeta) -> None:
        self._t = min(self._t + 1, self._t1)

        self._ma.update(candle.close)

        if self._t >= self._t1:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                self._advice = Advice.LONG
            elif candle.close <= lowest:
                self._advice = Advice.SHORT
            elif (self._advice is Advice.LONG and candle.close <= self._ma.value) or (
                self._advice is Advice.SHORT and candle.close >= self._ma.value
            ):
                self._advice = Advice.LIQUIDATE

        self._prices.append(candle.close)
