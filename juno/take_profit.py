from abc import ABC, abstractmethod
from decimal import Decimal

from juno import Candle


class TakeProfit(ABC):
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


class NoopTakeProfit(TakeProfit):
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


class BasicTakeProfit(TakeProfit):
    threshold: Decimal = Decimal('0.0')  # 0 means disabled.
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal) -> None:
        assert 0 <= threshold
        self.threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return (
            self.threshold > 0
            and self._close >= self._close_at_position * (1 + self.threshold)
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self.threshold > 0
            and self._close <= self._close_at_position * (1 - self.threshold)
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
