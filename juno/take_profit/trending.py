from decimal import Decimal
from typing import Callable, Optional

import pytweening

from juno import Candle
from juno.indicators import Adx
from juno.math import lerp

from .take_profit import TakeProfit

_EASINGS = {
    "linear": pytweening.linear,
    "quad_in": pytweening.easeInQuad,
    "quad_out": pytweening.easeOutQuad,
    "quad_inout": pytweening.easeInOutQuad,
    "cubic_in": pytweening.easeInCubic,
    "cubic_out": pytweening.easeOutCubic,
    "cubic_inout": pytweening.easeInOutCubic,
    "quart_in": pytweening.easeInQuart,
    "quart_out": pytweening.easeOutQuart,
    "quart_inout": pytweening.easeInOutQuart,
    "quint_in": pytweening.easeInQuint,
    "quint_out": pytweening.easeOutQuint,
    "quint_inout": pytweening.easeInOutQuint,
    "sine_in": pytweening.easeInSine,
    "sine_out": pytweening.easeOutSine,
    "sine_inout": pytweening.easeInOutSine,
    "circ_in": pytweening.easeInCirc,
    "circ_out": pytweening.easeOutCirc,
    "circ_inout": pytweening.easeInOutCirc,
    "expo_in": pytweening.easeInExpo,
    "expo_out": pytweening.easeOutExpo,
    "expo_inout": pytweening.easeInOutExpo,
    "elastic_in": pytweening.easeInElastic,
    "elastic_out": pytweening.easeOutElastic,
    "elastic_inout": pytweening.easeInOutElastic,
    "back_in": pytweening.easeInBack,
    "back_out": pytweening.easeOutBack,
    "back_inout": pytweening.easeInOutBack,
    "bounce_in": pytweening.easeInBounce,
    "bounce_out": pytweening.easeOutBounce,
    "bounce_inout": pytweening.easeInOutBounce,
}


class Trending(TakeProfit):
    _up_min_threshold: Decimal
    _up_max_threshold: Decimal
    _down_min_threshold: Decimal
    _down_max_threshold: Decimal
    _lock_threshold: bool
    _easing: str
    _up_threshold_factor: Decimal = Decimal("0.0")
    _down_threshold_factor: Decimal = Decimal("0.0")
    _adx: Adx
    _close_at_position: Decimal = Decimal("0.0")
    _close: Decimal = Decimal("0.0")

    def __init__(
        self,
        up_thresholds: tuple[Decimal, Decimal],
        down_thresholds: Optional[tuple[Decimal, Decimal]] = None,
        period: int = 14,
        lock_threshold: bool = False,
        easing: str = "linear",
    ) -> None:
        if down_thresholds is None:
            down_thresholds = up_thresholds
        assert 0 <= up_thresholds[0] and 0 <= up_thresholds[1]
        assert 0 <= down_thresholds[0] and 0 <= down_thresholds[1]
        self._up_min_threshold = up_thresholds[0]
        self._up_max_threshold = up_thresholds[1]
        self._down_min_threshold = down_thresholds[0]
        self._down_max_threshold = down_thresholds[1]
        self._lock_threshold = lock_threshold
        self._adx = Adx(period)
        self._easing = easing

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
        # The ADX value is essentially a progress from 0..1. Hence we can apply easing function
        # directly on it.
        adx_value = self._adx.value / 100
        progress = self._ease(adx_value)
        up_threshold = lerp(self._up_min_threshold, self._up_max_threshold, progress)
        down_threshold = lerp(self._down_min_threshold, self._down_max_threshold, progress)
        self._up_threshold_factor = 1 + up_threshold
        self._down_threshold_factor = 1 - down_threshold

    @property
    def _ease(self) -> Callable[[Decimal], Decimal]:
        easing_fn = _EASINGS.get(self._easing)
        if easing_fn is None:
            raise ValueError(f"Unknown easing function: {self._easing}")
        return easing_fn
