import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional, TypeVar

from juno import Interval, Timestamp
from juno.components import Chandler, Events, Prices
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.statistics import analyse_benchmark, analyse_portfolio
from juno.storages import Memory, Storage
from juno.strategies import Strategy
from juno.time import time_ms
from juno.traders import Multi
from juno.utils import format_as_config

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


# TODO: Consolidate into existing backtest agent.
class MultiBacktest(Agent):
    class Config(NamedTuple):
        exchange: str
        interval: Interval
        quote: Decimal
        strategy: Dict[str, Any]
        name: Optional[str] = None
        persist: bool = False
        start: Optional[Timestamp] = None
        end: Optional[Timestamp] = None
        trailing_stop: Decimal = Decimal('0.0')
        long: bool = True
        short: bool = False
        track: List[str] = []
        track_count: int = 4
        position_count: int = 2
        fiat_exchange: Optional[str] = None
        fiat_asset: str = 'usdt'

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(
        self,
        trader: Multi,
        chandler: Chandler,
        prices: Optional[Prices] = None,
        events: Events = Events(),
        storage: Storage = Memory(),
    ) -> None:
        self._trader = trader
        self._chandler = chandler
        self._prices = prices
        self._events = events
        self._storage = storage

    async def on_running(self, config: Config, state: State) -> None:
        await super().on_running(config, state)

        now = time_ms()

        start = None if config.start is None else floor_multiple(config.start, config.interval)
        end = now if config.end is None else config.end
        end = floor_multiple(end, config.interval)

        assert end <= now
        assert start is None or end > start
        assert config.quote > 0

        strategy_name, strategy_kwargs = get_type_name_and_kwargs(config.strategy)
        trader_config = Multi.Config(
            exchange=config.exchange,
            interval=config.interval,
            start=start,
            end=end,
            quote=config.quote,
            strategy=strategy_name,
            strategy_kwargs=strategy_kwargs,
            channel=state.name,
            trailing_stop=config.trailing_stop,
            long=config.long,
            short=config.short,
            track_count=config.track_count,
            track=config.track,
            position_count=config.position_count,
        )
        if not state.result:
            state.result = Multi.State()
        await self._trader.run(trader_config, state.result)
        assert (summary := state.result.summary)

        if not self._prices:
            _log.warning('skipping analysis; prices component not available')
            return

        _log.info('analysing trading summary')

        # Fetch necessary market data.
        symbols = (
            [p.symbol for p in state.result.summary.get_positions()]
            + [f'btc-{config.fiat_asset}']  # Use BTC as benchmark.
        )
        fiat_daily_prices = await self._prices.map_prices(
            exchange=config.exchange,
            symbols=symbols,
            fiat_asset=config.fiat_asset,
            fiat_exchange=config.fiat_exchange,
            start=summary.start,
            end=summary.end,
        )

        benchmark = analyse_benchmark(fiat_daily_prices['btc'])
        portfolio = analyse_portfolio(benchmark.g_returns, fiat_daily_prices, summary)

        _log.info(f'benchmark stats: {format_as_config(benchmark.stats)}')
        _log.info(f'portfolio stats: {format_as_config(portfolio.stats)}')

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(state.result.summary)}'
        )
        await self._events.emit(state.name, 'finished', state.result.summary)
