import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, NamedTuple, Optional

from juno import Interval, Timestamp
from juno.components import Events, Informant
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.storages import Memory, Storage
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import format_as_config

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Paper(Agent):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        quote: Decimal
        strategy: Dict[str, Any]
        name: Optional[str] = None
        persist: bool = False
        end: Timestamp = MAX_TIME_MS
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = True
        trailing_stop: Decimal = Decimal('0.0')
        long: bool = True
        short: bool = False

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Trader.State] = None

    def __init__(
        self, informant: Informant, trader: Trader, events: Events = Events(),
        storage: Storage = Memory(), get_time_ms: Callable[[], int] = time_ms
    ) -> None:
        self._informant = informant
        self._trader = trader
        self._events = events
        self._storage = storage
        self._get_time_ms = get_time_ms

        assert self._trader.broker

    async def on_running(self, config: Config, state: State) -> None:
        await Agent.on_running(self, config, state)

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
        if not state.result:
            state.result = Trader.State()
        await self._trader.run(trader_config, state.result)

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(state.result.summary)}'
        )
        await self._events.emit(state.name, 'finished', state.result.summary)
