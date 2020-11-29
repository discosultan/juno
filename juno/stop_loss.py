from abc import ABC, abstractmethod
from decimal import Decimal

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
    threshold: Decimal
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal) -> None:
        assert 0 <= threshold <= 1
        self.threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return self._close <= self._close_at_position * (1 - self.threshold)

    @property
    def downside_hit(self) -> bool:
        return self._close >= self._close_at_position * (1 + self.threshold)

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close


class Trailing(StopLoss):
    threshold: Decimal
    _highest_close_since_position = Decimal('0.0')
    _lowest_close_since_position = Decimal('Inf')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal) -> None:
        assert 0 <= threshold <= 1
        self.threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return self._close <= self._highest_close_since_position * (1 - self.threshold)

    @property
    def downside_hit(self) -> bool:
        return self._close >= self._lowest_close_since_position * (1 + self.threshold)

    def clear(self, candle: Candle) -> None:
        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)


class Legacy(StopLoss):
    threshold: Decimal  # 0 means disabled.
    trail: bool
    _close_at_position: Decimal = Decimal('0.0')
    _highest_close_since_position = Decimal('0.0')
    _lowest_close_since_position = Decimal('Inf')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal = Decimal('0.0'), trail: bool = True) -> None:
        assert 0 <= threshold < 1
        self.threshold = threshold
        self.trail = trail

    @property
    def upside_hit(self) -> bool:
        return (
            self.threshold > 0
            and (
                self._close
                <= (self._highest_close_since_position if self.trail else self._close_at_position)
                * (1 - self.threshold)
            )
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self.threshold > 0
            and (
                self._close
                >= (self._lowest_close_since_position if self.trail else self._close_at_position)
                * (1 + self.threshold)
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
