from abc import ABC, abstractmethod
from decimal import Decimal

from juno import Candle
from juno.indicators import Adx
from juno.math import lerp


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


class Noop(TakeProfit):
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


class Basic(TakeProfit):
    threshold: Decimal
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal) -> None:
        assert 0 <= threshold
        self.threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return self._close >= self._close_at_position * (1 + self.threshold)

    @property
    def downside_hit(self) -> bool:
        return self._close <= self._close_at_position * (1 - self.threshold)

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close


class Trending(TakeProfit):
    min_threshold: Decimal
    max_threshold: Decimal
    lock_threshold: bool
    _threshold: Decimal = Decimal('0.0')
    _adx: Adx

    def __init__(
        self, min_threshold: Decimal, max_threshold: Decimal, period: int,
        lock_threshold: bool = False
    ) -> None:
        assert 0 <= min_threshold and 0 <= max_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.lock_threshold = lock_threshold
        self._adx = Adx(period)

    @property
    def upside_hit(self) -> bool:
        return self._close >= self._close_at_position * (1 + self._threshold)

    @property
    def downside_hit(self) -> bool:
        return self._close <= self._close_at_position * (1 - self._threshold)

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close
        if self.lock_threshold:
            self._threshold = self._get_threshold()

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._adx.update(candle.high, candle.low)
        if not self.lock_threshold:
            self._threshold = self._get_threshold()

    def _get_threshold(self) -> Decimal:
        # Linear.
        # TODO: Support other interpolation functions.
        adx_value = self._adx.value / 100
        return lerp(self.min_threshold, self.max_threshold, adx_value)
