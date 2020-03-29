import logging
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional, TypeVar, get_type_hints

from typing_inspect import is_generic_type

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
        long: bool = True
        short: bool = False

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

    def __init__(
        self, informant: Informant, wallet: Wallet, trader: Trader, storage: Storage,
        event: Event = Event(), get_time_ms: Callable[[], int] = time_ms
    ) -> None:
        super().__init__(event)
        self._informant = informant
        self._wallet = wallet
        self._trader = trader
        self._storage = storage
        self._get_time_ms = get_time_ms

    async def on_running(self, config: Config, state: Agent.State) -> None:
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
            test=False,
            channel=state.name,
            missed_candle_policy=config.missed_candle_policy,
            adjust_start=config.adjust_start,
            trailing_stop=config.trailing_stop,
            long=config.long,
            short=config.short,
        )
        state.result = (
            await self._get_or_create_trader_state(trader_config, state) if config.store_state
            else Trader.State()
        )
        await self._trader.run(trader_config, state.result)

    async def on_finally(self, config: Config, state: Agent.State) -> None:
        _log.info(f'trading summary: {format_as_config(state.result.summary)}')
        if config.store_state:
            await self._save_trader_state(state)

    async def _get_or_create_trader_state(
        self, trader_config: Trader.Config, state: Agent.State
    ) -> Trader.State:
        # Create dummy strategy from config to figure out runtime type.
        dummy_strategy = trader_config.new_strategy()
        strategy_type = type(dummy_strategy)
        if is_generic_type(strategy_type):
            resolved_params = _resolve_generic_types(dummy_strategy)  # type: ignore
            # TODO: Can we spread it into type?
            if len(resolved_params) == 1:
                strategy_type = strategy_type[resolved_params[0]]  # type: ignore
            elif len(resolved_params) == 2:
                strategy_type = strategy_type[resolved_params[0], resolved_params[1]]  # type: ignore
            elif len(resolved_params) > 2:
                raise NotImplementedError()
        existing_state = await self._storage.get(
            'default',
            self._get_storage_key(state),
            Agent.State[Trader.State[strategy_type]],  # type: ignore
        )
        if not existing_state:
            _log.info(f'existing state with name {state.name} not found; starting new')
            return Trader.State()
        if existing_state.status in [AgentStatus.RUNNING, AgentStatus.FINISHED]:
            raise NotImplementedError()
        _log.info(
            f'existing live session with name {existing_state.name} found; continuing previous'
        )
        return existing_state.result

    async def _save_trader_state(self, state: Agent.State) -> None:
        _log.info(f'storing current state with name {state.name} and status {state.status.name}')
        await self._storage.set(
            'default',
            self._get_storage_key(state),
            state,
        )

    def _get_storage_key(self, state: Agent.State) -> str:
        return f'{type(self).__name__.lower()}_{state.name}_state'


def _resolve_generic_types(container: Any) -> List[type]:
    result = []
    container_type = type(container)
    generic_params = container_type.__parameters__
    type_hints = get_type_hints(container_type)
    for generic_param in generic_params:
        name = next(k for k, v in type_hints.items() if v is generic_param)
        result.append(type(getattr(container, name)))
    return result
