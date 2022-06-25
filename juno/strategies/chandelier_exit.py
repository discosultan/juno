from __future__ import annotations

from juno import Advice, Candle, CandleMeta, indicators

from .strategy import Changed, Signal


class ChandelierExit(Signal):
    _advice: Advice = Advice.NONE
    _chandelier: indicators.ChandelierExit
    _changed: Changed

    def __init__(
        self,
        long_period: int = 22,
        short_period: int = 22,
        atr_period: int = 22,
        atr_multiplier: int = 3,
    ) -> None:
        self._chandelier = indicators.ChandelierExit(
            long_period=long_period,
            short_period=short_period,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
        )
        self._changed = Changed(enabled=True)

    @property
    def advice(self) -> Advice:
        return self._advice if self.mature else Advice.NONE

    @property
    def maturity(self) -> int:
        return self._chandelier.maturity

    @property
    def mature(self) -> bool:
        return self._chandelier.mature

    def update(self, candle: Candle, _: CandleMeta) -> None:
        if candle.close > self._chandelier.short:
            self._advice = self._changed.update(Advice.LONG)
        elif candle.close < self._chandelier.long:
            self._advice = self._changed.update(Advice.SHORT)
        else:
            self._advice = Advice.NONE
        self._chandelier.update(high=candle.high, low=candle.low, close=candle.close)
