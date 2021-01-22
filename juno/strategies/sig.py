from typing import Any

from juno import Advice, Candle, strategies
from juno.config import init_module_instance

from .strategy import MidTrend, MidTrendPolicy, Persistence, Signal


# Generic signal with additional persistence and mid trend filters.
class Sig(Signal):
    _advice: Advice = Advice.NONE
    _sig: Signal
    _mid_trend: MidTrend
    _persistence: Persistence
    _t: int = 0
    _t1: int

    def __init__(
        self,
        sig: dict[str, Any],
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
    ) -> None:
        self._sig = init_module_instance(strategies, sig)
        self._mid_trend = MidTrend(mid_trend_policy)
        self._persistence = Persistence(level=persistence, return_previous=False)
        self._t1 = (
            self._sig.maturity
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

        if self._sig.mature:
            self._advice = Advice.combine(
                self._mid_trend.update(self._sig.advice),
                self._persistence.update(self._sig.advice),
            )
