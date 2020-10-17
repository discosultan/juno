from typing import Any, Dict, Tuple, Union

from juno import Advice, Candle
from juno.constraints import Constraint, Int

from .strategy import MidTrend, MidTrendPolicy, Persistence, mid_trend_policy_choices


# Generic signal + oscillator with additional persistence and mid trend filters.
class SigOsc:
    class Meta:
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {
            'persistence': Int(0, 10),
            'mid_trend_policy': mid_trend_policy_choices,
        }

    _advice: Advice = Advice.NONE
    _sig: Any
    _osc: Any
    _mid_trend: MidTrend
    _persistence: Persistence
    _t: int = 0
    _t1: int

    def __init__(
        self,
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
    ) -> None:
        self._mid_trend = MidTrend(mid_trend_policy)
        self._persistence = Persistence(level=persistence, return_previous=False)
        self._t1 = (
            max(self._sig.maturity, self._osc.maturity)
            + max(self._mid_trend.maturity, self._persistence.maturity)
            - 1
        )

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, candle: Candle) -> Advice:
        self._t = min(self._t + 1, self._t1)

        advice = self._sig.update(candle)
        self._osc.update(candle)

        if self._sig.mature and self._osc.mature:
            if (
                advice is Advice.LONG and not self._osc.oversold
                or advice is Advice.SHORT and not self._osc.overbought
            ):
                advice = Advice.LIQUIDATE

            self._advice = Advice.combine(
                self._mid_trend.update(advice),
                self._persistence.update(advice),
            )

        return self._advice
