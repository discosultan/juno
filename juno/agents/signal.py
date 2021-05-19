import logging
from typing import Any, NamedTuple, Optional

from juno import Advice, Interval, strategies
from juno.candles import Chandler
from juno.components import Events
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple_offset
from juno.storages import Memory, Storage
from juno.strategies import Changed
from juno.time import time_ms
from juno.utils import get_module_type

from .agent import Agent

_log = logging.getLogger(__name__)


class Signal(Agent):
    class Config(NamedTuple):
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

        now = time_ms()
        interval_offset = self._chandler.get_interval_offset(config.exchange, config.interval)
        start = floor_multiple_offset(now, config.interval, interval_offset)
        start -= (strategy.maturity - 1) * config.interval

        changed = Changed(True)

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=config.symbol,
            interval=config.interval,
            start=start,
        ):
            advice = strategy.update(candle)
            _log.info(f'received advice: {advice.name}')
            advice = changed.update(advice)
            if advice is not Advice.NONE:
                await self._events.emit(state.name, 'message', advice.name)
