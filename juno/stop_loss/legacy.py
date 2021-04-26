from decimal import Decimal

from juno import Candle

from .stop_loss import StopLoss


class Legacy(StopLoss):
    _threshold: Decimal  # 0 means disabled.
    _trail: bool
    _close_at_position: Decimal = Decimal('0.0')
    _highest_close_since_position = Decimal('0.0')
    _lowest_close_since_position = Decimal('Inf')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal = Decimal('0.0'), trail: bool = True) -> None:
        assert 0 <= threshold < 1
        self._threshold = threshold
        self._trail = trail

    @property
    def upside_hit(self) -> bool:
        return self._threshold > 0 and (
            self._close
            <= (self._highest_close_since_position if self._trail else self._close_at_position)
            * (1 - self._threshold)
        )

    @property
    def downside_hit(self) -> bool:
        return self._threshold > 0 and (
            self._close
            >= (self._lowest_close_since_position if self._trail else self._close_at_position)
            * (1 + self._threshold)
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close
        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)
