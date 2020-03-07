import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import (
    Any, Callable, Dict, Generic, List, NamedTuple, Optional, TypeVar, get_type_hints
)

from juno import Interval, Timestamp
from juno.components import Event, Informant, Wallet
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.storages import Storage
from juno.strategies import Strategy
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import format_as_config, unpack_symbol

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


class Live(Agent):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        strategy: Dict[str, Any]
        name: Optional[str] = None
        quote: Optional[Decimal] = None
        end: Timestamp = MAX_TIME_MS
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = True
        trailing_stop: Decimal = Decimal('0.0')
        store_state: bool = True

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

    @dataclass
    class State(Generic[TStrategy]):
        status: AgentStatus
        name: str
        result: Trader.State[TStrategy]

    def __init__(
        self, informant: Informant, wallet: Wallet, trader: Trader, storage: Storage,
        event: Event = Event(), get_time_ms: Optional[Callable[[], int]] = None
    ) -> None:
        super().__init__(event)
        self._informant = informant
        self._wallet = wallet
        self._trader = trader
        self._storage = storage
        self._get_time_ms = get_time_ms or time_ms

    async def on_running(self, config: Config, state: State) -> None:
        current = floor_multiple(self._get_time_ms(), config.interval)
        end = floor_multiple(config.end, config.interval)
        assert end > current

        available_quote = self._wallet.get_balance(config.exchange, config.quote_asset).available

        _, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert available_quote > filters.price.min

        quote = config.quote
        if quote is None:
            quote = available_quote
            _log.info(f'quote not defined; using available {available_quote} {config.quote_asset}')
        else:
            assert quote <= available_quote
            _log.info(f'using pre-defined quote {quote} {config.quote_asset}')

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader_config = Trader.Config(
            exchange=config.exchange,
            symbol=config.symbol,
            interval=config.interval,
            start=current,
            end=end,
            quote=quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            test=True,  # TODO: TEMP
            channel=state.name,
            missed_candle_policy=config.missed_candle_policy,
            adjust_start=config.adjust_start,
            trailing_stop=config.trailing_stop,
        )
        state.result = (
            await self._get_or_create_trader_state(trader_config, state.name) if config.store_state
            else Trader.State()
        )
        await self._trader.run(trader_config, state.result)
        if config.store_state:
            await self._save_trader_state(state)

    async def on_cancelled(self, config: Config, state: State) -> None:
        if config.store_state:
            await self._save_trader_state(state)

    async def on_errored(self, config: Config, state: State) -> None:
        if config.store_state:
            await self._save_trader_state(state)

    async def on_finally(self, config: Config, state: State) -> None:
        _log.info(f'trading summary: {format_as_config(state.result.summary)}')

    async def _get_or_create_trader_state(
        self, trader_config: Trader.Config, name: str
    ) -> Trader.State:
        # Create dummy strategy from config to figure out runtime type.
        dummy_strategy = trader_config.new_strategy()
        strategy_type = type(dummy_strategy)
        resolved_params = _resolve_generic_types(dummy_strategy)  # type: ignore
        if len(resolved_params) == 1:
            strategy_type = strategy_type[resolved_params[0]]  # type: ignore
        elif len(resolved_params) == 2:
            strategy_type = strategy_type[resolved_params[0], resolved_params[1]]  # type: ignore
        elif len(resolved_params) > 2:
            raise NotImplementedError()
        trader_state_type = Trader.State[strategy_type]  # type: ignore
        state = await self._storage.get(
            'default',
            f'{name}_live_trader_state',
            Live.State[trader_state_type],  # type: ignore
        )
        if not state:
            _log.info(f'existing state with name {name} not found; starting new')
            return Trader.State()
        if state.status in [AgentStatus.RUNNING, AgentStatus.FINISHED]:
            raise NotImplementedError()
        _log.info(f'existing live session with name {name} found; continuing previous')
        return state.result

    async def _save_trader_state(self, state: State) -> None:
        _log.info(f'storing current state with name {state.name} and status {state.status.name}')
        await self._storage.set('default', f'{state.name}_live_trader_state', state)


def _resolve_generic_types(container: Any) -> List[type]:
    result = []
    container_type = type(container)
    generic_params = container_type.__parameters__
    type_hints = get_type_hints(container_type)
    for generic_param in generic_params:
        name = next(k for k, v in type_hints.items() if v is generic_param)
        result.append(type(getattr(container, name)))
    return result
