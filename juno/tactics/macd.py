import operator
from typing import Dict, Tuple, Union

from juno import Advice, Candle, indicators
from juno.constraints import Constraint, Int, Pair


# Simple MACD based strategy which signals buy when MACD value above the signal line and sell if
# below.
class Macd:
    class Meta:
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {
            ('short_period', 'long_period'): Pair(Int(1, 100), operator.lt, Int(2, 101)),
            'signal_period': Int(1, 101),
            'persistence': Int(0, 10),
        }

    _macd: indicators.Macd

    def __init__(
        self,
        short_period: int = 12,
        long_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        self._macd = indicators.Macd(short_period, long_period, signal_period)

    @property
    def maturity(self) -> int:
        return self._macd.maturity

    @property
    def mature(self) -> bool:
        return self._macd.mature

    def update(self, candle: Candle) -> Advice:
        self._macd.update(candle.close)

        if self.mature:
            if self._macd.value > self._macd.signal:
                return Advice.LONG
            else:
                return Advice.SHORT

        return Advice.NONE
