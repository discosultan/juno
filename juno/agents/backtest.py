import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno.components import Chandler, Informant
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import time_ms
from juno.trading import Trader

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        super().__init__()
        self.chandler = chandler
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Optional[int] = None,
        missed_candle_policy: str = 'ignore',
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
    ) -> None:
        now = time_ms()

        if end is None:
            end = floor_multiple(now, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        trader = Trader(
            chandler=self.chandler,
            informant=self.informant,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote,
            new_strategy=lambda: new_strategy(strategy_config),
            event=self,
            log=_log,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = trader.summary
        await trader.run()
