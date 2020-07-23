from decimal import Decimal
from typing import Dict

from juno import Candle, indicators
from juno.constraints import Constraint, Int, Uniform


class Mmi:
    class Meta:
        constraints: Dict[str, Constraint] = {
            'period': Int(200, 500),
            'threshold': Uniform(Decimal('0.01'), Decimal('99.99')),
        }

    _mmi: indicators.Mmi
    _threshold: Decimal

    def __init__(
        self,
        period: int = 200,
        threshold: Decimal = Decimal('0.75'),
    ) -> None:
        self._mmi = indicators.Mmi(period)
        self._threshold = threshold

    @property
    def maturity(self) -> int:
        return self._mmi.maturity

    def update(self, candle: Candle) -> None:
        self._mmi.update(candle.close)
        if self._mmi.mature:
            if self._mmi.value < self._threshold:
                # Non trending.?
                pass
            else:
                # Trending.
                pass
