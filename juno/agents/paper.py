import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, NamedTuple, Optional

from juno import Interval, Timestamp, stop_loss, strategies, take_profit
from juno.components import Events, Informant
from juno.config import (
    format_as_config,
    get_module_type_constructor,
    get_type_name_and_kwargs,
    kwargs_for,
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
        trader: dict[str, Any]
        strategy: dict[str, Any]
        stop_loss: Optional[dict[str, Any]] = None
        take_profit: Optional[dict[str, Any]] = None
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
        traders: list[Trader],
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
            stop_loss=(
                None if config.stop_loss is None
                else get_module_type_constructor(stop_loss, config.stop_loss)
            ),
            take_profit=(
                None if config.take_profit is None
                else get_module_type_constructor(take_profit, config.take_profit)
            ),
            mode=TradingMode.PAPER,
            channel=state.name,
        )
        if not state.result:
            state.result = await trader.initialize(trader_config)

        _log.info(f'{self.get_name(state)}: running with config {format_as_config(config)}')
        await self._events.emit(state.name, 'starting', config, state, trader)

        await trader.run(state.result)

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(extract_public(state.result.summary))}'
        )
        await self._events.emit(state.name, 'finished', state.result.summary)
