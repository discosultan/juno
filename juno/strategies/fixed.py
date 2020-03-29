import logging
from typing import List

from juno import Advice, Candle

from .strategy import Strategy

_log = logging.getLogger(__name__)


class Fixed(Strategy):
    advices: List[Advice]
    updates: List[Candle]

    def __init__(
        self, advices: List[str] = [], persistence: int = 0,
        allow_initial: bool = False, maturity: int = 0
    ) -> None:
        super().__init__(maturity=maturity, persistence=persistence, allow_initial=allow_initial)
        self.advices = [Advice[a.upper()] for a in advices]
        self.updates = []

    def tick(self, candle: Candle) -> Advice:
        self.updates.append(candle)
        if len(self.advices) > 0:
            return self.advices.pop(0)
        _log.warning('ran out of predetermined advices; no more advice given')
        return Advice.NONE
