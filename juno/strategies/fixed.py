import asyncio
import logging
from typing import List

from juno import Advice, Candle

from .strategy import Strategy

_log = logging.getLogger(__name__)


class Fixed(Strategy):
    advices: List[Advice]
    updates: List[Candle]
    cancel: bool

    def __init__(
        self,
        advices: List[str] = [],
        maturity: int = 0,
        ignore_mid_trend: bool = False,
        persistence: int = 0,
        cancel: bool = False,
    ) -> None:
        super().__init__(
            maturity=maturity,
            persistence=persistence,
            ignore_mid_trend=ignore_mid_trend,
        )
        self.advices = [Advice[a.upper()] for a in advices]
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
