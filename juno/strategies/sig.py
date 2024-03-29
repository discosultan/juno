from typing import Any

from juno import Advice, Candle, CandleMeta, strategies
from juno.config import init_module_instance

from .strategy import Changed, Maturity, MidTrend, MidTrendPolicy, Persistence, Signal


# Generic signal with additional persistence and mid trend filters.
class Sig(Signal):
    _advice: Advice = Advice.NONE
    _sig: Signal
    _mid_trend: MidTrend
    _persistence: Persistence
    _extra_maturity: Maturity
    _changed: Changed
    _t: int = 0
    _t1: int

    def __init__(
        self,
        sig: dict[str, Any],
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
        extra_maturity: int = 0,
        changed_enabled: bool = False,
    ) -> None:
        self._sig = init_module_instance(strategies, sig)
        self._mid_trend = MidTrend(mid_trend_policy)
        self._persistence = Persistence(level=persistence, return_previous=False)
        self._extra_maturity = Maturity(maturity=extra_maturity)
        self._changed = Changed(enabled=changed_enabled)
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

    def update(self, candle: Candle, meta: CandleMeta) -> None:
        self._t = min(self._t + 1, self._t1)

        self._sig.update(candle, meta)

        extra_maturity_advice = self._extra_maturity.update(self._changed.update(self._sig.advice))

        if self._sig.mature:
            mid_trend_advice = self._mid_trend.update(self._sig.advice)
            persistence_advice = self._persistence.update(self._sig.advice)

            self._advice = Advice.combine(
                extra_maturity_advice,
                mid_trend_advice,
                persistence_advice,
            )
