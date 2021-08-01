from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from juno import Advice, Candle, strategies
from juno.config import init_module_instance

from .strategy import MidTrend, MidTrendPolicy, Oscillator, Persistence, Signal


@dataclass
class SigOscParams:
    sig: Any
    osc: Any
    osc_filter: str = "enforce"
    mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT
    persistence: int = 0

    def construct(self) -> SigOsc:
        return SigOsc(self)


# Generic signal with additional oscillator, persistence and mid trend filters.
#
# In order for the signal to be valid, the oscillator must be, in case of:
# - 'enforce' filter - oversold when going long, or overbought when going short
# - 'prevent' filter - not overbought when going long, and not oversold when going short
class SigOsc(Signal):
    _advice: Advice = Advice.NONE
    _sig: Signal
    _osc: Oscillator
    _osc_filter: str
    _mid_trend: MidTrend
    _persistence: Persistence
    _t: int = 0
    _t1: int

    def __init__(self, params: SigOscParams) -> None:
        assert params.osc_filter in ["enforce", "prevent"]

        self._sig = init_module_instance(strategies, params.sig)
        self._osc = init_module_instance(strategies, params.osc)
        self._osc_filter = params.osc_filter
        self._mid_trend = MidTrend(params.mid_trend_policy)
        self._persistence = Persistence(level=params.persistence, return_previous=False)
        self._t1 = (
            max(self._sig.maturity, self._osc.maturity)
            + max(self._mid_trend.maturity, self._persistence.maturity)
            - 1
        )

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, candle: Candle) -> None:
        self._t = min(self._t + 1, self._t1)

        self._sig.update(candle)
        self._osc.update(candle)

        if self._sig.mature and self._osc.mature:
            advice = self._sig.advice

            if self._osc_filter == "enforce":
                advice = self._osc_enforce(advice)
            else:
                advice = self._osc_prevent(advice)

            self._advice = Advice.combine(
                self._mid_trend.update(advice),
                self._persistence.update(advice),
            )

    def _osc_enforce(self, advice: Advice) -> Advice:
        return (
            Advice.LIQUIDATE
            if (
                advice is Advice.LONG
                and not self._osc.oversold
                or advice is Advice.SHORT
                and not self._osc.overbought
            )
            else advice
        )

    def _osc_prevent(self, advice: Advice) -> Advice:
        return (
            Advice.LIQUIDATE
            if (
                advice is Advice.LONG
                and self._osc.overbought
                or advice is Advice.SHORT
                and self._osc.oversold
            )
            else advice
        )
