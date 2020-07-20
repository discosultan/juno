from decimal import Decimal
from typing import Dict

from juno import Candle, indicators
from juno.constraints import Constraint, Int, Uniform


class Adx:
    class Meta:
        constraints: Dict[str, Constraint] = {
            'period': Int(1, 365),
            'threshold': Uniform(Decimal('0.01'), Decimal('99.99')),
        }

    _adx: indicators.Adx
    _threshold: Decimal

    def __init__(
        self,
        period: int = 28,
        threshold: Decimal = Decimal('0.25'),
    ) -> None:
        self._adx = indicators.Adx(period)
        self._threshold = threshold

    @property
    def maturity(self) -> int:
        return self._adx.maturity

    def update(self, candle: Candle) -> None:
        self._adx.update(candle.high, candle.low)
        if self._adx.mature:
            if self._adx.value < self._threshold:
                # Non trending.
                pass
            else:
                # Trending.
                pass
