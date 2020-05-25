import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Events, Informant
from juno.config import get_module_type_constructor, get_type_name_and_kwargs, kwargs_for
from juno.math import floor_multiple
from juno.storages import Memory, Storage
from juno.time import MAX_TIME_MS, time_ms
from juno.traders import Trader
from juno.utils import extract_public, format_as_config

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Paper(Agent):
    class Config(NamedTuple):
        exchange: str
        interval: Interval
        quote: Decimal
        trader: Dict[str, Any]
        strategy: Dict[str, Any]
        name: Optional[str] = None
        persist: bool = False
        end: Timestamp = MAX_TIME_MS

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(
        self, informant: Informant, traders: List[Trader], events: Events = Events(),
        storage: Storage = Memory(), get_time_ms: Callable[[], int] = time_ms
    ) -> None:
        self._informant = informant
        self._traders = {type(t).__name__.lower(): t for t in traders}
        self._trader = traders
        self._events = events
        self._storage = storage
        self._get_time_ms = get_time_ms

        assert all(t.broker for t in self._traders.values())

    async def on_running(self, config: Config, state: State) -> None:
        await Agent.on_running(self, config, state)

        current = floor_multiple(self._get_time_ms(), config.interval)
        end = floor_multiple(config.end, config.interval)
        assert end > current

        trader_name, trader_kwargs = get_type_name_and_kwargs(config.trader)
        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader = self._traders[trader_name]
        trader_config = trader.Config(
            exchange=config.exchange,
            interval=config.interval,
            start=current,
            end=end,
            quote=config.quote,
            strategy=get_module_type_constructor(strategies, config.strategy),
            test=True,
            channel=state.name,
            **kwargs_for(trader.Config, trader_kwargs),
        )
        if not state.result:
            state.result = trader.State()
        await trader.run(trader_config, state.result)

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(extract_public(state.result.summary))}'
        )
        await self._events.emit(state.name, 'finished', state.result.summary)
