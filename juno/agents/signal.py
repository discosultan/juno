import logging
from dataclasses import dataclass
from typing import Any, Optional

from juno import Advice, Interval, Timestamp_, strategies
from juno.components import Chandler, Events
from juno.config import get_type_name_and_kwargs
from juno.inspect import get_module_type
from juno.storages import Memory, Storage
from juno.strategies import Changed

from .agent import Agent

_log = logging.getLogger(__name__)


class Signal(Agent):
    @dataclass(frozen=True)
    class Config:
        exchange: str
        symbol: str
        interval: Interval
        strategy: dict[str, Any]
        name: Optional[str] = None

    def __init__(
        self,
        chandler: Chandler,
        events: Events = Events(),
        storage: Storage = Memory(),
    ) -> None:
        self._chandler = chandler
        self._events = events
        self._storage = storage

    async def on_running(self, config: Config, state: Agent.State) -> None:
        await super().on_running(config, state)

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        strategy = get_module_type(strategies, strategy_name)(**strategy_kwargs)

        now = Timestamp_.now()
        start = Timestamp_.floor(now, config.interval)
        start -= (strategy.maturity - 1) * config.interval

        changed = Changed(True)

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=config.symbol,
            interval=config.interval,
            start=start,
        ):
            advice = strategy.update(candle)
            _log.info(f"received advice: {advice.name}")
            advice = changed.update(advice)
            if advice is not Advice.NONE:
                await self._events.emit(state.name, "message", advice.name)
