import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Interval, Timestamp
from juno.components import Event, Informant
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import format_as_config

from .agent import Agent

_log = logging.getLogger(__name__)


class Paper(Agent):
    def __init__(self, informant: Informant, trader: Trader, event: Event = Event()) -> None:
        super().__init__(event)
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

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(strategy)
        config = Trader.Config(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=current,
            end=end,
            quote=quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            test=True,
            channel=self.name,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = Trader.State()
        await self._trader.run(config, self.result)

    def on_finally(self) -> None:
        _log.info(f'trading summary: {format_as_config(self.result.summary)}')
