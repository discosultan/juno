import logging
from decimal import Decimal
from typing import Any, Dict, NamedTuple, Optional, TypeVar

from typing_inspect import is_generic_type

from juno import Interval, Timestamp
from juno.components import Event, Historian, Prices
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.storages import Memory, Storage
from juno.strategies import Strategy
from juno.time import time_ms
from juno.trading import MissedCandlePolicy, Trader, analyse_benchmark, analyse_portfolio
from juno.typing import resolve_generic_types
from juno.utils import format_as_config, unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


class Backtest(Agent):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        quote: Decimal
        strategy: Dict[str, Any]
        name: Optional[str] = None
        persist: bool = False
        start: Optional[Timestamp] = None
        end: Optional[Timestamp] = None
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = True
        trailing_stop: Decimal = Decimal('0.0')
        long: bool = True
        short: bool = False

        @property
        def base_asset(self) -> str:
            return unpack_symbol(self.symbol)[0]

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

    def __init__(
        self,
        trader: Trader,
        historian: Optional[Historian] = None,
        prices: Optional[Prices] = None,
        event: Event = Event(),
        storage: Storage = Memory(),
    ) -> None:
        self._trader = trader
        self._historian = historian
        self._prices = prices
        self._event = event
        self._storage = storage

    async def on_running(self, config: Any, state: Agent.State[Trader.State]) -> None:
        await super().on_running(config, state)

        start = config.start
        if self._historian:
            first_candle = await self._historian.find_first_candle(
                config.exchange, config.symbol, config.interval
            )
            if not start or start < first_candle.time:
                start = first_candle.time

        if start is None:
            raise ValueError('Must manually specify backtest start time; historian not configured')

        now = time_ms()

        start = floor_multiple(start, config.interval)
        end = config.end
        if end is None:
            end = now
        end = floor_multiple(end, config.interval)

        assert end <= now
        assert end > start
        assert config.quote > 0

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader_config = Trader.Config(
            exchange=config.exchange,
            symbol=config.symbol,
            interval=config.interval,
            start=start,
            end=end,
            quote=config.quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            channel=state.name,
            missed_candle_policy=config.missed_candle_policy,
            adjust_start=config.adjust_start,
            trailing_stop=config.trailing_stop,
            long=config.long,
            short=config.short,
        )
        await self._trader.run(trader_config, state.result)
        assert state.result.summary

        if not self._prices:
            return

        # Fetch necessary market data.
        fiat_daily_prices = await self._prices.map_fiat_daily_prices(
            (config.base_asset, config.quote_asset), start, end
        )

        benchmark = analyse_benchmark(fiat_daily_prices['btc'])
        portfolio = analyse_portfolio(
            benchmark.g_returns, fiat_daily_prices, state.result.summary
        )

        _log.info(f'benchmark stats: {format_as_config(benchmark.stats)}')
        _log.info(f'portfolio stats: {format_as_config(portfolio.stats)}')

    async def on_finally(self, config: Config, state: Agent.State[Trader.State]) -> None:
        _log.info(
            f'{self._get_name(state)}: finished with result '
            f'{format_as_config(state.result.summary)}'
        )
        await self._event.emit(state.name, 'finished', state.result.summary)

    def _get_result_type(self, config: Config) -> type:
        # Create dummy trader config to be able to resolve strategy type.
        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        dummy_trader_config = Trader.Config(
            exchange='dummy',
            symbol='dummy',
            interval=1,
            start=0,
            end=1,
            quote=Decimal('1.0'),
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
        )
        # Create dummy strategy from config to figure out runtime type.
        dummy_strategy = dummy_trader_config.new_strategy()
        strategy_type = type(dummy_strategy)
        if is_generic_type(strategy_type):
            resolved_params = resolve_generic_types(dummy_strategy)  # type: ignore
            # TODO: Can we spread it into type? `strategy_type[*resolved_params]` is invalid.
            if len(resolved_params) == 1:
                strategy_type = strategy_type[resolved_params[0]]  # type: ignore
            elif len(resolved_params) == 2:
                strategy_type = strategy_type[
                    resolved_params[0], resolved_params[1]
                ]  # type: ignore
            elif len(resolved_params) > 2:
                raise NotImplementedError()
        return Trader.State[strategy_type]  # type: ignore
