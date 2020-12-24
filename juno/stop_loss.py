from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from juno import Candle


class StopLoss(ABC):
    @property
    @abstractmethod
    def upside_hit(self) -> bool:
        pass

    @property
    @abstractmethod
    def downside_hit(self) -> bool:
        pass

    @abstractmethod
    def clear(self, candle: Candle) -> None:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> None:
        pass


class Noop(StopLoss):
    @property
    def upside_hit(self) -> bool:
        return False

    @property
    def downside_hit(self) -> bool:
        return False

    def clear(self, candle: Candle) -> None:
        pass

    def update(self, candle: Candle) -> None:
        pass


class Basic(StopLoss):
    _up_threshold_factor: Decimal
    _down_threshold_factor: Decimal
    _closed: bool
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(
        self,
        up_threshold: Decimal,
        down_threshold: Optional[Decimal] = None,
        closed: bool = True,
    ) -> None:
        if down_threshold is None:
            down_threshold = up_threshold
        assert 0 <= up_threshold <= 1
        assert 0 <= down_threshold <= 1
        self._up_threshold_factor = 1 - up_threshold
        self._down_threshold_factor = 1 + down_threshold
        self._closed = closed

    @property
    def upside_hit(self) -> bool:
        return self._close <= self._close_at_position * self._up_threshold_factor

    @property
    def downside_hit(self) -> bool:
        return self._close >= self._close_at_position * self._down_threshold_factor

    def clear(self, candle: Candle) -> None:
        if self._closed and not candle.closed:
            return

        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        if self._closed and not candle.closed:
            return

        self._close = candle.close


class Trailing(StopLoss):
    _up_threshold_factor: Decimal
    _down_threshold_factor: Decimal
    _closed: bool
    _highest_close_since_position = Decimal('0.0')
    _lowest_close_since_position = Decimal('Inf')
    _close: Decimal = Decimal('0.0')

    def __init__(
        self,
        up_threshold: Decimal,
        down_threshold: Optional[Decimal] = None,
        closed: bool = True,
    ) -> None:
        if down_threshold is None:
            down_threshold = up_threshold
        assert 0 <= up_threshold <= 1
        assert 0 <= down_threshold <= 1
        self._up_threshold_factor = 1 - up_threshold
        self._down_threshold_factor = 1 + down_threshold
        self._closed = closed

    @property
    def upside_hit(self) -> bool:
        return self._close <= self._highest_close_since_position * self._up_threshold_factor

    @property
    def downside_hit(self) -> bool:
        return self._close >= self._lowest_close_since_position * self._down_threshold_factor

    def clear(self, candle: Candle) -> None:
        if self._closed and not candle.closed:
            return

        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        if self._closed and not candle.closed:
            return

        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)


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
        return (
            self._threshold > 0
            and (
                self._close
                <= (self._highest_close_since_position if self._trail else self._close_at_position)
                * (1 - self._threshold)
            )
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self._threshold > 0
            and (
                self._close
                >= (self._lowest_close_since_position if self._trail else self._close_at_position)
                * (1 + self._threshold)
            )
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close
        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)
