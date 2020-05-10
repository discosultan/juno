import logging
from typing import Any, Dict, NamedTuple, Optional

from juno import Advice, Interval, strategies
from juno.components import Chandler, Event
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.modules import get_module_type
from juno.storages import Memory, Storage
from juno.strategies import Changed
from juno.time import time_ms

from .agent import Agent

_log = logging.getLogger(__name__)


class Signal(Agent):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        strategy: Dict[str, Any]
        name: Optional[str] = None

    def __init__(
        self,
        chandler: Chandler,
        event: Event = Event(),
        storage: Storage = Memory(),
    ) -> None:
        self._chandler = chandler
        self._event = event
        self._storage = storage

    async def on_running(self, config: Config, state: Agent.State) -> None:
        await super().on_running(config, state)

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        strategy = get_module_type(strategies, strategy_name)(**strategy_kwargs)

        now = time_ms()
        start = floor_multiple(now, config.interval)
        start -= strategy.adjust_hint * config.interval

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
                await self._event.emit(state.name, 'advice', advice)
