from decimal import Decimal

from juno import Advice, Candle, CandleMeta, indicators

from .strategy import Signal


class DarvasBox(Signal):
    _darvas_box: indicators.DarvasBox
    _advice: Advice = Advice.NONE
    _previous_close: Decimal = Decimal("NaN")

    def __init__(self, boxp: int = 5) -> None:
        self._darvas_box = indicators.DarvasBox(boxp)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._darvas_box.maturity

    @property
    def mature(self) -> bool:
        return self._darvas_box.mature

    def update(self, candle: Candle, meta: CandleMeta) -> None:
        self._darvas_box.update(high=candle.high, low=candle.low)

        if not self._previous_close.is_nan():
            if (
                self._previous_close < self._darvas_box.top_box
                and candle.close > self._darvas_box.top_box
            ):
                self._advice = Advice.LONG
            elif (
                self._previous_close > self._darvas_box.bottom_box
                and candle.close < self._darvas_box.bottom_box
            ):
                self._advice = Advice.SHORT

        self._previous_close = candle.close
