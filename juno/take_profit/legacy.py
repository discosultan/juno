from decimal import Decimal

from juno import Candle

from .take_profit import TakeProfit


class Legacy(TakeProfit):
    _threshold: Decimal  # 0 means disabled.
    _close_at_position: Decimal = Decimal("0.0")
    _close: Decimal = Decimal("0.0")

    def __init__(self, threshold: Decimal = Decimal("0.0")) -> None:
        assert 0 <= threshold
        self._threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return self._threshold > 0 and self._close >= self._close_at_position * (
            1 + self._threshold
        )

    @property
    def downside_hit(self) -> bool:
        return self._threshold > 0 and self._close <= self._close_at_position * (
            1 - self._threshold
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
