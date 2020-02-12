import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Prices
from juno.config import init_module_instance
from juno.math import floor_multiple
from juno.time import time_ms
from juno.trading import (
    MissedCandlePolicy, Trader, TradingSummary, get_benchmark_statistics, get_portfolio_statistics
)
from juno.utils import unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    def __init__(self, trader: Trader, prices: Optional[Prices] = None) -> None:
        super().__init__()
        self.trader = trader
        self.prices = prices

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        start: Timestamp,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Optional[Timestamp] = None,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
    ) -> None:
        now = time_ms()

        start = floor_multiple(start, interval)
        if end is None:
            end = now
        end = floor_multiple(end, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        self.result = TradingSummary(start=start, quote=quote)
        await self.trader.run(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote,
            new_strategy=lambda: init_module_instance(strategies, strategy_config),
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
            summary=self.result
        )

        if not self.prices:
            return

        # Fetch necessary market data.
        base_asset, quote_asset = unpack_symbol(symbol)
        fiat_daily_prices = await self.prices.map_fiat_daily_prices(
            (base_asset, quote_asset), start, end
        )

        benchmark_stats = get_benchmark_statistics(fiat_daily_prices['btc'])
        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, fiat_daily_prices, self.result
        )

        _log.info(f'benchmark stats: {benchmark_stats}')
        _log.info(f'portfolio stats: {portfolio_stats}')
