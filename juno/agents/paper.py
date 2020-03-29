import logging
from decimal import Decimal
from typing import Any, Callable, Dict, NamedTuple, Optional

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
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        quote: Decimal
        strategy: Dict[str, Any]
        name: Optional[str] = None
        end: Timestamp = MAX_TIME_MS
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = True
        trailing_stop: Decimal = Decimal('0.0')
        long: bool = True
        short: bool = False

    def __init__(
        self, informant: Informant, trader: Trader, event: Event = Event(),
        get_time_ms: Callable[[], int] = time_ms
    ) -> None:
        super().__init__(event)
        self._informant = informant
        self._trader = trader
        self._get_time_ms = get_time_ms

        assert self._trader.has_broker

    async def on_running(self, config: Config, state: Agent.State[Trader.State]) -> None:
        current = floor_multiple(self._get_time_ms(), config.interval)
        end = floor_multiple(config.end, config.interval)
        assert end > current

        fees, filters = self._informant.get_fees_filters(config.exchange, config.symbol)

        assert config.quote > filters.price.min

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader_config = Trader.Config(
            exchange=config.exchange,
            symbol=config.symbol,
            interval=config.interval,
            start=current,
            end=end,
            quote=config.quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            test=True,
            channel=state.name,
            missed_candle_policy=config.missed_candle_policy,
            adjust_start=config.adjust_start,
            trailing_stop=config.trailing_stop,
            long=config.long,
            short=config.short,
        )
        state.result = Trader.State()
        await self._trader.run(trader_config, state.result)

    async def on_finally(self, config: Config, state: Agent.State[Trader.State]) -> None:
        if state.result:
            _log.info(f'trading summary: {format_as_config(state.result.summary)}')
