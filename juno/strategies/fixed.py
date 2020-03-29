import logging
from typing import List, Optional

from juno import Advice, Candle

from .strategy import Strategy

_log = logging.getLogger(__name__)


class Fixed(Strategy):
    advices: List[Advice]
    updates: List[Candle]

    def __init__(
        self, advices: Optional[List[Advice]] = None, allow_initial: bool = False,
        maturity: int = 0
    ) -> None:
        super().__init__(maturity=maturity, allow_initial=allow_initial)
        self.advices = [] if advices is None else advices
        self.updates = []

    def tick(self, candle: Candle) -> Advice:
        self.updates.append(candle)
        if len(self.advices) > 0:
            return self.advices.pop(0)
        _log.warning('ran out of predetermined advices; no more advice given')
        return Advice.NONE