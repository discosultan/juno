from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from juno import Advice, Candle, strategies
from juno.config import init_module_instance

from .strategy import Maturity, MidTrend, MidTrendPolicy, Persistence, Signal


@dataclass
class SigParams:
    sig: Any
    mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT
    persistence: int = 0
    extra_maturity: int = 0

    def construct(self) -> Sig:
        return Sig(self)


# Generic signal with additional persistence and mid trend filters.
class Sig(Signal):
    _advice: Advice = Advice.NONE
    _sig: Signal
    _mid_trend: MidTrend
    _persistence: Persistence
    _extra_maturity: Maturity
    _t: int = 0
    _t1: int

    def __init__(self, params: SigParams) -> None:
        self._sig = init_module_instance(strategies, params.sig)
        self._mid_trend = MidTrend(params.mid_trend_policy)
        self._persistence = Persistence(level=params.persistence, return_previous=False)
        self._extra_maturity = Maturity(maturity=params.extra_maturity)
        self._t1 = max(
            self._sig.maturity + max(self._mid_trend.maturity, self._persistence.maturity) - 1,
            self._extra_maturity.maturity,
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

        extra_maturity_advice = self._extra_maturity.update(self._sig.advice)

        if self._sig.mature:
            self._advice = Advice.combine(
                self._mid_trend.update(self._sig.advice),
                self._persistence.update(self._sig.advice),
                extra_maturity_advice,
            )
