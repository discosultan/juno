import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional

from juno import (
    Interval,
    Timestamp,
    Timestamp_,
    json,
    serialization,
    stop_loss,
    strategies,
    take_profit,
)
from juno.components import Events, Informant
from juno.config import get_module_type_constructor, get_type_name_and_kwargs, kwargs_for
from juno.inspect import construct
from juno.statistics.core import CoreStatistics
from juno.storages import Storage
from juno.traders import Trader
from juno.trading import TradingMode, TradingSummary

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Live(Agent):
    @dataclass(frozen=True)
    class Config:
        exchange: str
        interval: Interval
        trader: dict[str, Any]
        strategy: dict[str, Any]
        stop_loss: Optional[dict[str, Any]] = None
        take_profit: Optional[dict[str, Any]] = None
        name: Optional[str] = None
        persist: bool = False
        quote: Optional[Decimal] = None
        end: Optional[Timestamp] = None
        custodian: str = "spot"

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(
        self,
        informant: Informant,
        traders: list[Trader],
        storage: Storage,
        events: Events = Events(),
        get_time_ms: Callable[[], int] = Timestamp_.now,
    ) -> None:
        self._informant = informant
        self._traders = {type(t).__name__.lower(): t for t in traders}
        self._storage = storage
        self._events = events
        self._get_time_ms = get_time_ms

        assert all(t.broker for t in self._traders.values())

    async def on_running(self, config: Config, state: State) -> None:
        now = self._get_time_ms()

        assert config.end is None or config.end > now

        start = now
        end = Timestamp_.MAX_TIME if config.end is None else config.end

        trader_name, trader_kwargs = get_type_name_and_kwargs(config.trader)
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
                None
                if config.stop_loss is None
                else get_module_type_constructor(stop_loss, config.stop_loss)
            ),
            take_profit=(
                None
                if config.take_profit is None
                else get_module_type_constructor(take_profit, config.take_profit)
            ),
            mode=TradingMode.LIVE,
            channel=state.name,
            custodian=config.custodian,
        )
        if not state.result:
            state.result = await trader.initialize(trader_config)

        _log.info(
            f"{self.get_name(state)}: running with config "
            f"{json.dumps(serialization.config.serialize(config), indent=4)}"
        )
        await self._events.emit(state.name, "starting", config, state, trader)

        await trader.run(state.result)

    async def on_finally(self, config: Config, state: State) -> Any:
        summary = self.build_summary(config, state)
        stats = CoreStatistics.compose(summary)
        _log.info(
            f"{self.get_name(state)}: finished with result "
            f"{json.dumps(serialization.config.serialize(stats), indent=4)}"
        )
        await self._events.emit(state.name, "finished", summary)
        return summary

    def build_summary(self, config: Config, state: State) -> TradingSummary:
        assert state.result
        trader_name, _ = get_type_name_and_kwargs(config.trader)
        trader = self._traders[trader_name]
        return trader.build_summary(state.result)
