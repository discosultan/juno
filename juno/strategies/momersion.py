from decimal import Decimal

from juno import Candle, indicators
from juno.constraints import Int, Uniform

from .strategy import Strategy


class Momersion(Strategy):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                "period": Int(100, 500),
                "threshold": Uniform(Decimal("0.01"), Decimal("99.99")),
            }
        )

    _momersion: indicators.Momersion
    _threshold: Decimal

    def __init__(
        self,
        period: int = 250,
        threshold: Decimal = Decimal("0.50"),
    ) -> None:
        self._momersion = indicators.Momersion(period)
        self._threshold = threshold

    @property
    def maturity(self) -> int:
        return self._momersion.maturity

    @property
    def mature(self) -> bool:
        return self._momersion.mature

    def update(self, candle: Candle) -> None:
        self._momersion.update(candle.close)
        if self._momersion.mature:
            if self._momersion.value < self._threshold:
                # Non trending.
                pass
            else:
                # Trending.
                pass
