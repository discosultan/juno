from decimal import Decimal
from typing import Dict

from juno import Candle, indicators
from juno.constraints import Constraint, Int, Uniform


# TODO: For example, well-known market technician Constance Brown, CMT, has promoted the idea that
# an oversold reading on the RSI in an uptrend is likely much higher than 30%, and an overbought
# reading on the RSI during a downtrend is much lower than the 70% level.
class Rsi:
    @staticmethod
    class Meta:
        constraints: Dict[str, Constraint] = {
            'period': Int(1, 101),
            'up_threshold': Uniform(Decimal('50.0'), Decimal('100.0')),
            'down_threshold': Uniform(Decimal('0.0'), Decimal('50.0')),
        }

    _rsi: indicators.Rsi
    _up_threshold: Decimal
    _down_threshold: Decimal

    def __init__(
        self,
        period: int = 14,
        up_threshold: Decimal = Decimal('70.0'),
        down_threshold: Decimal = Decimal('30.0'),
    ) -> None:
        assert period > 0
        assert up_threshold > down_threshold

        self._rsi = indicators.Rsi(period)
        self._up_threshold = up_threshold
        self._down_threshold = down_threshold

    @property
    def maturity(self) -> int:
        return self._rsi.maturity

    @property
    def overbought(self) -> bool:
        return self._rsi.mature and self._rsi.value >= self._up_threshold

    @property
    def oversold(self) -> bool:
        return self._rsi.mature and self._rsi.value <= self._down_threshold

    def tick(self, candle: Candle) -> None:
        self._rsi.update(candle.close)
