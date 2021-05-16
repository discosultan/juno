import asyncio
import logging

from juno import Advice
from juno.candles import Candle

from .strategy import MidTrend, MidTrendPolicy, Persistence, Signal

_log = logging.getLogger(__name__)


class Fixed(Signal):
    advices: list[Advice]
    updates: list[Candle]
    cancel: bool

    _advice: Advice = Advice.NONE
    _maturity: int
    _mid_trend: MidTrend
    _persistence: Persistence
    _t: int = 0
    _t1: int
    _t2: int

    def __init__(
        self,
        advices: list[Advice] = [],
        maturity: int = 1,
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
        cancel: bool = False,
    ) -> None:
        self.advices = list(advices)
        self.updates = []
        self.cancel = cancel

        self._maturity = maturity
        self._mid_trend = MidTrend(mid_trend_policy)
        self._persistence = Persistence(level=persistence, return_previous=False)
        self._t1 = maturity
        self._t2 = maturity + max(self._mid_trend.maturity, self._persistence.maturity) - 1

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    def update(self, candle: Candle) -> None:
        self._t = min(self._t + 1, self._t2)

        self.updates.append(candle)
        if len(self.advices) > 0:
            self._advice = self.advices.pop(0)
            if self._t >= self._t1:
                self._advice = Advice.combine(
                    self._mid_trend.update(self._advice),
                    self._persistence.update(self._advice),
                )
        else:
            if self.cancel:
                _log.info('cancelling as no more advice defined')
                current_task = asyncio.current_task()
                assert current_task
                current_task.cancel()
            else:
                _log.warning('ran out of predetermined advices; no more advice given')
            self._advice = Advice.NONE
