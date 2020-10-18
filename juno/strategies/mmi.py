from decimal import Decimal

from juno import Candle, indicators
from juno.constraints import Int, Uniform

from .strategy import Strategy


class Mmi(Strategy):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                'period': Int(200, 500),
                'threshold': Uniform(Decimal('0.01'), Decimal('99.99')),
            }
        )

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

    @property
    def mature(self) -> bool:
        return self._mmi.mature

    def update(self, candle: Candle) -> None:
        self._mmi.update(candle.close)
        if self._mmi.mature:
            if self._mmi.value < self._threshold:
                # Non trending.?
                pass
            else:
                # Trending.
                pass
