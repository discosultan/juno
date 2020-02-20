import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Historian, Prices
from juno.config import get_module_type_and_config
from juno.math import floor_multiple
from juno.time import time_ms
from juno.trading import (
    MissedCandlePolicy, Trader, TradingSummary, analyse_benchmark, analyse_portfolio
)
from juno.utils import unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    def __init__(
        self,
        trader: Trader,
        historian: Optional[Historian] = None,
        prices: Optional[Prices] = None,
    ) -> None:
        super().__init__()
        self._trader = trader
        self._historian = historian
        self._prices = prices

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        quote: Decimal,
        strategy: Dict[str, Any],
        start: Optional[Timestamp] = None,
        end: Optional[Timestamp] = None,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
    ) -> None:
        if self._historian:
            first_candle = await self._historian.find_first_candle(exchange, symbol, interval)
            if not start or start < first_candle.time:
                start = first_candle.time

        if start is None:
            raise ValueError('Must manually specify backtest start time; historian not configured')

        now = time_ms()

        start = floor_multiple(start, interval)
        if end is None:
            end = now
        end = floor_multiple(end, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        strategy_type, strategy_config = get_module_type_and_config(strategies, strategy)
        self.result = TradingSummary(start=start, quote=quote)
        await self._trader.run(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote,
            strategy_type=strategy_type,
            strategy_kwargs=strategy_config,
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
            summary=self.result
        )

        _log.info(f'trading summary: {self.format_as_config(self.result)}')

        if not self._prices:
            return

        # Fetch necessary market data.
        base_asset, quote_asset = unpack_symbol(symbol)
        fiat_daily_prices = await self._prices.map_fiat_daily_prices(
            (base_asset, quote_asset), start, end
        )

        benchmark = analyse_benchmark(fiat_daily_prices['btc'])
        portfolio = analyse_portfolio(
            benchmark.g_returns, fiat_daily_prices, self.result
        )

        _log.info(f'benchmark stats: {self.format_as_config(benchmark.stats)}')
        _log.info(f'portfolio stats: {self.format_as_config(portfolio.stats)}')
