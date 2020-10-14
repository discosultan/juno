import asyncio
import logging
from typing import List

from juno import Advice, Candle

from .strategy import MidTrend, MidTrendPolicy, Persistence

_log = logging.getLogger(__name__)


class Fixed:
    advices: List[Advice]
    updates: List[Candle]
    cancel: bool

    _maturity: int
    _mid_trend: MidTrend
    _persistence: Persistence
    _t: int = 0

    def __init__(
        self,
        advices: List[Advice] = [],
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

    @property
    def maturity(self) -> int:
        return self._maturity

    @property
    def mature(self) -> bool:
        return self._t >= self._maturity

    def tick(self, candle: Candle) -> Advice:
        self._t = min(self._t + 1, self._maturity)

        self.updates.append(candle)
        if len(self.advices) > 0:
            return self.advices.pop(0)
        if self.cancel:
            _log.info('cancelling as no more advice defined')
            current_task = asyncio.current_task()
            assert current_task
            current_task.cancel()
        else:
            _log.warning('ran out of predetermined advices; no more advice given')
        return Advice.NONE
