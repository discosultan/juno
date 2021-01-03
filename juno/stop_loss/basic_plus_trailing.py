from decimal import Decimal
from typing import Optional

from juno import Candle

from .basic import Basic
from .stop_loss import StopLoss
from .trailing import Trailing


class BasicPlusTrailing(StopLoss):
    _basic: Basic
    _trailing: Trailing

    def __init__(
        self,
        up_threshold: Decimal,
        up_trailing_threshold: Decimal,
        down_threshold: Optional[Decimal] = None,
        down_trailing_threshold: Optional[Decimal] = None,
    ) -> None:
        self._basic = Basic(
            up_threshold=up_threshold,
            down_threshold=down_threshold,
        )
        self._trailing = Trailing(
            up_threshold=up_trailing_threshold,
            down_threshold=down_trailing_threshold,
        )

    @property
    def upside_hit(self) -> bool:
        return self._basic.upside_hit or self._trailing.upside_hit

    @property
    def downside_hit(self) -> bool:
        return self._basic.downside_hit or self._trailing.downside_hit

    def clear(self, candle: Candle) -> None:
        self._basic.clear(candle)
        self._trailing.clear(candle)

    def update(self, candle: Candle) -> None:
        self._basic.update(candle)
        self._trailing.update(candle)
