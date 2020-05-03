import logging
from decimal import Decimal
from typing import Any, Callable, Dict, NamedTuple, Optional, TypeVar

from juno import Interval, Timestamp
from juno.components import Event, Informant, Wallet
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.storages import Storage
from juno.strategies import Strategy
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import unpack_symbol

from .agent import Agent
from .backtest import Backtest

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


class Live(Backtest):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        strategy: Dict[str, Any]
        name: Optional[str] = None
        persist: bool = False
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
        self._informant = informant
        self._wallet = wallet
        self._trader = trader
        self._storage = storage
        self._event = event
        self._get_time_ms = get_time_ms

        assert self._trader.broker

    async def on_running(self, config: Config, state: Agent.State) -> None:
        await Agent.on_running(self, config, state)

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
        await self._trader.run(trader_config, state.result)
