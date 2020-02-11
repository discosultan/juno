from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Informant
from juno.config import init_module_instance
from juno.math import floor_multiple
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader, TradingResult

from .agent import Agent


class Paper(Agent):
    def __init__(self, informant: Informant, trader: Trader) -> None:
        super().__init__()
        self.informant = informant
        self.trader = trader

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Timestamp = MAX_TIME_MS,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
        get_time_ms: Optional[Callable[[], int]] = None,
    ) -> None:
        if not get_time_ms:
            get_time_ms = time_ms

        current = floor_multiple(get_time_ms(), interval)
        end = floor_multiple(end, interval)
        assert end > current

        _, filters = self.informant.get_fees_filters(exchange, symbol)

        assert quote > filters.price.min

        self.result = TradingResult(quote=quote)
        await self.trader.run(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=current,
            end=end,
            quote=quote,
            new_strategy=lambda: init_module_instance(strategies, strategy_config),
            test=True,
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
            result=self.result
        )
