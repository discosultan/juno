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
    _up_threshold_factor: Decimal
    _down_threshold_factor: Decimal
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, up_threshold: Decimal, down_threshold: Decimal) -> None:
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


class Trending(TakeProfit):
    _up_min_threshold: Decimal
    _up_max_threshold: Decimal
    _down_min_threshold: Decimal
    _down_max_threshold: Decimal
    _lock_threshold: bool
    _up_threshold_factor: Decimal = Decimal('0.0')
    _down_threshold_factor: Decimal = Decimal('0.0')
    _adx: Adx
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(
        self,
        up_min_threshold: Decimal,
        up_max_threshold: Decimal,
        down_min_threshold: Decimal,
        down_max_threshold: Decimal,
        period: int,
        lock_threshold: bool = False
    ) -> None:
        assert 0 <= up_min_threshold and 0 <= up_max_threshold
        assert 0 <= down_min_threshold and 0 <= down_max_threshold
        self._up_min_threshold = up_min_threshold
        self._up_max_threshold = up_max_threshold
        self._down_min_threshold = down_min_threshold
        self._down_max_threshold = down_max_threshold
        self._lock_threshold = lock_threshold
        self._adx = Adx(period)

    @property
    def upside_hit(self) -> bool:
        return self._close >= self._close_at_position * self._up_threshold_factor

    @property
    def downside_hit(self) -> bool:
        return self._close <= self._close_at_position * self._down_threshold_factor

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close
        if self._lock_threshold:
            self._set_thresholds()

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._adx.update(candle.high, candle.low)
        if not self._lock_threshold:
            self._set_thresholds()

    def _set_thresholds(self) -> None:
        # Linear.
        # TODO: Support other interpolation functions.
        adx_value = self._adx.value / 100
        up_threshold = lerp(self._up_min_threshold, self._up_max_threshold, adx_value)
        down_threshold = lerp(self._down_min_threshold, self._down_max_threshold, adx_value)
        self._up_threshold_factor = 1 + up_threshold
        self._down_threshold_factor = 1 - down_threshold


class Legacy(TakeProfit):
    _threshold: Decimal  # 0 means disabled.
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    def __init__(self, threshold: Decimal = Decimal('0.0')) -> None:
        assert 0 <= threshold
        self._threshold = threshold

    @property
    def upside_hit(self) -> bool:
        return (
            self._threshold > 0
            and self._close >= self._close_at_position * (1 + self._threshold)
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self._threshold > 0
            and self._close <= self._close_at_position * (1 - self._threshold)
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
