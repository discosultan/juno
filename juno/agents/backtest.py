from decimal import Decimal
from typing import Any, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Chandler, Informant
from juno.config import init_module_instance
from juno.math import floor_multiple
from juno.time import time_ms
from juno.trading import (
    MissedCandlePolicy, Trader, get_alpha_beta, get_benchmark_statistics, get_portfolio_statistics
)

from .agent import Agent


class Backtest(Agent):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        super().__init__()
        self.chandler = chandler
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        start: Timestamp,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Optional[Timestamp] = None,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
    ) -> None:
        now = time_ms()

        start = floor_multiple(start, interval)
        if end is None:
            end = now
        end = floor_multiple(end, interval)

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
            new_strategy=lambda: init_module_instance(strategies, strategy_config),
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = trader.summary
        await trader.run()

        await analyze(self.chandler, self.informant, exchange, symbol, trader.summary)
