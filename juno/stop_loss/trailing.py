from decimal import Decimal
from typing import Optional

from juno import Candle

from .stop_loss import StopLoss


class Trailing(StopLoss):
    _up_threshold_factor: Decimal
    _down_threshold_factor: Decimal
    _highest_close_since_position = Decimal("0.0")
    _lowest_close_since_position = Decimal("Inf")
    _close: Decimal = Decimal("0.0")

    def __init__(self, up_threshold: Decimal, down_threshold: Optional[Decimal] = None) -> None:
        if down_threshold is None:
            down_threshold = up_threshold
        assert 0 <= up_threshold <= 1
        assert 0 <= down_threshold <= 1
        self._up_threshold_factor = 1 - up_threshold
        self._down_threshold_factor = 1 + down_threshold

    @property
    def upside_hit(self) -> bool:
        return self._close <= self._highest_close_since_position * self._up_threshold_factor

    @property
    def downside_hit(self) -> bool:
        return self._close >= self._lowest_close_since_position * self._down_threshold_factor

    def clear(self, candle: Candle) -> None:
        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)
