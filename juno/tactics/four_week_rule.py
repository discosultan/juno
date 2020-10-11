from collections import deque
from decimal import Decimal
from typing import Deque, Dict

from juno import Advice, Candle, indicators
from juno.constraints import Constraint, Int
from juno.indicators import MA, Sma
from juno.math import minmax
from juno.utils import get_module_type

from .common import ma_choices


# Signals a long position when a candle close price goes above a highest four week close price.
# Signals a short position when a candle close price goes below a lowest four week close price.
# Signals liquidation when a candle close price crosses a two week moving average.
# Works with daily candles!
class FourWeekRule:
    class Meta:
        constraints: Dict[str, Constraint] = {
            'period': Int(2, 100),
            'ma': ma_choices,
            'ma_period': Int(2, 100),
        }

    _prices: Deque[Decimal]
    _ma: MA
    _advice: Advice = Advice.NONE
    _t: int = 0
    _t1: int

    def __init__(
        self,
        period: int = 28,
        ma: str = Sma.__name__.lower(),
        ma_period: int = 14,  # Normally half the period.
    ) -> None:
        self._prices = deque(maxlen=period)
        self._ma = get_module_type(indicators, ma)(ma_period)
        self._t1 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, candle: Candle) -> Advice:
        self._t = min(self._t + 1, self._t1)

        self._ma.update(candle.close)

        if self._t >= self._t1:
            lowest, highest = minmax(self._prices)
            if candle.close >= highest:
                self._advice = Advice.LONG
            elif candle.close <= lowest:
                self._advice = Advice.SHORT
            elif (
                (self._advice is Advice.LONG and candle.close <= self._ma.value)
                or (self._advice is Advice.SHORT and candle.close >= self._ma.value)
            ):
                self._advice = Advice.LIQUIDATE

        self._prices.append(candle.close)
        return self._advice
