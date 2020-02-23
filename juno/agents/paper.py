import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Informant
from juno.config import get_module_type_and_config
from juno.math import floor_multiple
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader, TradingSummary
from juno.utils import format_as_config

from .agent import Agent

_log = logging.getLogger(__name__)


class Paper(Agent):
    def __init__(self, informant: Informant, trader: Trader) -> None:
        super().__init__()
        self._informant = informant
        self._trader = trader

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        quote: Decimal,
        strategy: Dict[str, Any],
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

        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        assert quote > filters.price.min

        strategy_type, strategy_config = get_module_type_and_config(strategies, strategy)
        self.result = TradingSummary(start=current, quote=quote)
        await self._trader.run(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=current,
            end=end,
            quote=quote,
            strategy_type=strategy_type,
            strategy_kwargs=strategy_config,
            test=True,
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
            summary=self.result
        )

    def on_finally(self) -> None:
        _log.info(f'trading summary: {format_as_config(self.result)}')
