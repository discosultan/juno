import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Events, Informant
from juno.config import (
    format_as_config, get_module_type_constructor, get_type_name_and_kwargs, kwargs_for
)
from juno.storages import Memory, Storage
from juno.time import MAX_TIME_MS, time_ms
from juno.traders import Trader
from juno.trading import TradingMode
from juno.utils import construct, extract_public

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
        end: Optional[Timestamp] = None

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(
        self,
        informant: Informant,
        traders: List[Trader],
        events: Events = Events(),
        storage: Storage = Memory(),
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._informant = informant
        self._traders = {type(t).__name__.lower(): t for t in traders}
        self._trader = traders
        self._events = events
        self._storage = storage
        self._get_time_ms = get_time_ms

        assert all(t.broker for t in self._traders.values())

    async def on_running(self, config: Config, state: State) -> None:
        await super().on_running(config, state)

        now = self._get_time_ms()

        assert config.end is None or config.end > now

        start = now
        end = MAX_TIME_MS if config.end is None else config.end

        trader_name, trader_kwargs = get_type_name_and_kwargs(config.trader)
        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader = self._traders[trader_name]

        trader_config_type = type(trader).config()
        trader_config = construct(
            trader_config_type,
            config,
            **kwargs_for(trader_config_type, trader_kwargs),
            start=start,
            end=end,
            strategy=get_module_type_constructor(strategies, config.strategy),
            mode=TradingMode.PAPER,
            channel=state.name,
        )
        if not state.result:
            state.result = await trader.initialize(trader_config)
        await trader.run(state.result)

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(extract_public(state.result.summary))}'
        )
        await self._events.emit(state.name, 'finished', state.result.summary)
