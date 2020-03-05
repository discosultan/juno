import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, Generic, Optional, TypeVar, get_type_hints

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


@dataclass
class _Session(Generic[TStrategy]):
    status: AgentStatus
    state: Trader.State[TStrategy]


class Live(Agent):
    def __init__(
        self, informant: Informant, wallet: Wallet, trader: Trader, storage: Storage,
        event: Event = Event()
    ) -> None:
        super().__init__(event)
        self._informant = informant
        self._wallet = wallet
        self._trader = trader
        self._storage = storage

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        strategy: Dict[str, Any],
        quote: Optional[Decimal] = None,
        end: Timestamp = MAX_TIME_MS,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
        get_time_ms: Optional[Callable[[], int]] = None,
        store_state: bool = False,
    ) -> None:
        if not get_time_ms:
            get_time_ms = time_ms

        current = floor_multiple(get_time_ms(), interval)
        end = floor_multiple(end, interval)
        assert end > current

        _, quote_asset = unpack_symbol(symbol)
        available_quote = self._wallet.get_balance(exchange, quote_asset).available

        _, filters = self._informant.get_fees_filters(exchange, symbol)
        assert available_quote > filters.price.min

        if quote is None:
            quote = available_quote
            _log.info(f'quote not defined; using available {available_quote} {quote_asset}')
        else:
            assert quote <= available_quote
            _log.info(f'using pre-defined quote {quote} {quote_asset}')

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(strategy)
        config = Trader.Config(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=current,
            end=end,
            quote=quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            test=True,  # TODO: TEMP
            channel=self.name,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = await self._get_or_create_state(config) if store_state else Trader.State()
        await self._trader.run(config, self.result)

    async def on_finally(self) -> None:
        _log.info(f'trading summary: {format_as_config(self.result.summary)}')
        if self.config.get('store_state'):
            await self._save_state(self.result)

    async def _get_or_create_state(self, config: Trader.Config) -> Trader.State[Any]:
        # Create dummy strategy from config to figure out runtime type.
        dummy_strategy = config.new_strategy()
        strategy_type = type(dummy_strategy)
        resolved_params = _resolve_generic_types(dummy_strategy)  # type: ignore
        if len(resolved_params) == 1:
            strategy_type = strategy_type[resolved_params[0]]  # type: ignore
        elif len(resolved_params) == 2:
            strategy_type = strategy_type[resolved_params[0], resolved_params[1]]  # type: ignore
        elif len(resolved_params) > 2:
            raise NotImplementedError()
        type_ = Trader.State[strategy_type]  # type: ignore
        session = await self._storage.get(
            'default',
            f'{self.name}_live_trader_state',
            _Session[type_],  # type: ignore
        )
        if not session:
            return Trader.State()
        if session.status in [AgentStatus.RUNNING, AgentStatus.FINISHED]:
            raise NotImplementedError()
        return session.state

    async def _save_state(self, state: Trader.State[Any]) -> None:
        await self._storage.set(
            'default',
            f'{self.name}_live_trader_state',
            _Session(status=self.status, state=state),
        )


def _resolve_generic_types(container):
    result = []
    container_type = type(container)
    generic_params = container_type.__parameters__
    type_hints = get_type_hints(container_type)
    for generic_param in generic_params:
        name = next(k for k, v in type_hints.items() if v is generic_param)
        result.append(type(getattr(container, name)))
    return result
