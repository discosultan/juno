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
    mid_trend: MidTrend
    persistence: Persistence

    def __init__(
        self,
        advices: List[Advice] = [],
        maturity: int = 1,
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
        cancel: bool = False,
    ) -> None:
        super().__init__(
            maturity=maturity,
            persistence=persistence,
            mid_trend_policy=mid_trend_policy,
        )
        self.advices = list(advices)
        self.updates = []
        self.cancel = cancel

    def tick(self, candle: Candle) -> Advice:
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
