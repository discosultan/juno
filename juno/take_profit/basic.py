from decimal import Decimal
from typing import Optional

from juno.candles import Candle

from .take_profit import TakeProfit


class Basic(TakeProfit):
    _up_threshold_factor: Decimal
    _down_threshold_factor: Decimal
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, up_threshold: Decimal, down_threshold: Optional[Decimal] = None) -> None:
        if down_threshold is None:
            down_threshold = up_threshold
        assert 0 <= up_threshold
        assert 0 <= down_threshold
        self._up_threshold_factor = 1 + up_threshold
        self._down_threshold_factor = 1 - down_threshold

    @property
    def upside_hit(self) -> bool:
        return self._close >= self._close_at_position * self._up_threshold_factor

    @property
    def downside_hit(self) -> bool:
        return self._close <= self._close_at_position * self._down_threshold_factor

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
