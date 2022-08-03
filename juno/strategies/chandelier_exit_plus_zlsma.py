from __future__ import annotations

from juno import Advice, Candle, CandleMeta, indicators

from .chandelier_exit import ChandelierExit
from .strategy import Changed, Signal


class ChandelierExitPlusZlsma(Signal):
    _advice: Advice = Advice.NONE
    _chandelier_exit: ChandelierExit
    _zlsma: indicators.Zlsma
    _changed: Changed

    def __init__(
        self,
        chandelier_exit_long_period: int = 22,
        chandelier_exit_short_period: int = 22,
        chandelier_exit_atr_period: int = 22,
        chandelier_exit_atr_multiplier: int = 3,
        zlsma_period: int = 50,
    ) -> None:
        self._chandelier_exit = ChandelierExit(
            long_period=chandelier_exit_long_period,
            short_period=chandelier_exit_short_period,
            atr_period=chandelier_exit_atr_period,
            atr_multiplier=chandelier_exit_atr_multiplier,
        )
        self._zlsma = indicators.Zlsma(period=zlsma_period)
        self._changed = Changed(enabled=True)

    @property
    def advice(self) -> Advice:
        return self._advice if self.mature else Advice.NONE

    @property
    def maturity(self) -> int:
        return max(self._chandelier_exit.maturity, self._zlsma.maturity)

    @property
    def mature(self) -> bool:
        return self._chandelier_exit.mature and self._zlsma.mature

    def update(self, candle: Candle, meta: CandleMeta) -> None:
        self._chandelier_exit.update(candle, meta)
        advice = self._chandelier_exit.advice
        zlsma = self._zlsma.update(candle.close)

        if advice is Advice.LONG and candle.close >= zlsma:
            self._advice = self._changed.update(Advice.LONG)
        elif advice is Advice.SHORT and candle.close <= zlsma:
            self._advice = self._changed.update(Advice.SHORT)
        elif self._changed.prevailing_advice is Advice.LONG and candle.close < zlsma:
            self._advice = self._changed.update(Advice.LIQUIDATE)
        elif self._changed.prevailing_advice is Advice.SHORT and candle.close > zlsma:
            self._advice = self._changed.update(Advice.LIQUIDATE)
        else:
            self._advice = Advice.NONE
