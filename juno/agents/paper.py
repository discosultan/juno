import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Interval, Timestamp
from juno.components import Event, Informant
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import format_as_config

from .agent import Agent, AgentConfig, AgentState

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperConfig(AgentConfig):
    exchange: str
    symbol: str
    interval: Interval
    quote: Decimal
    strategy: Dict[str, Any]
    end: Timestamp = MAX_TIME_MS
    missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
    adjust_start: bool = True
    trailing_stop: Decimal = Decimal('0.0')
    get_time_ms: Optional[Callable[[], int]] = None


@dataclass
class PaperState(AgentState):
    result: Trader.State


class Paper(Agent[PaperConfig, PaperState]):
    def __init__(self, informant: Informant, trader: Trader, event: Event = Event()) -> None:
        super().__init__(event)
        self._informant = informant
        self._trader = trader

    async def on_running(self, config: PaperConfig, state: PaperState) -> None:
        get_time_ms = config.get_time_ms if config.get_time_ms else time_ms

        current = floor_multiple(get_time_ms(), config.interval)
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
        )
        state.result = Trader.State()
        await self._trader.run(trader_config, state.result)

    async def on_finally(self, config: PaperConfig, state: PaperState) -> None:
        if state.result:
            _log.info(f'trading summary: {format_as_config(state.result.summary)}')
