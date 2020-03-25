import logging
from decimal import Decimal
from typing import Any, Dict, NamedTuple, Optional

from juno import Interval, Timestamp
from juno.components import Event, Historian, Prices
from juno.config import get_type_name_and_kwargs
from juno.math import floor_multiple
from juno.time import time_ms
from juno.trading import MissedCandlePolicy, Trader, analyse_benchmark, analyse_portfolio
from juno.utils import format_as_config, unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        quote: Decimal
        strategy: Dict[str, Any]
        name: Optional[str] = None
        start: Optional[Timestamp] = None
        end: Optional[Timestamp] = None
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = True
        trailing_stop: Decimal = Decimal('0.0')
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
    ) -> None:
        super().__init__(event)
        self._trader = trader
        self._historian = historian
        self._prices = prices

    async def on_running(self, config: Config, state: Agent.State[Trader.State]) -> None:
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
            short=config.short,
        )
        state.result = Trader.State()
        await self._trader.run(trader_config, state.result)
        assert state.result.summary

        _log.info(f'trading summary: {format_as_config(state.result.summary)}')

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
