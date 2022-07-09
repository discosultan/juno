import logging
from itertools import chain

from juno import Asset, Interval, Interval_, Symbol_, Timestamp_
from juno.components import Prices
from juno.contextlib import AsyncContextManager
from juno.trading import TradingSummary

from .statistics import Statistics

_log = logging.getLogger(__name__)


class Statistician(AsyncContextManager):
    def __init__(self, prices: Prices) -> None:
        self._prices = prices

    async def get_statistics(
        self,
        summary: TradingSummary,
        exchange: str,
        benchmark_asset: Asset = "btc",
        target_asset: Asset = "usdt",
        interval: Interval = Interval_.DAY,
    ) -> Statistics:
        _log.info(f"calculating benchmark and portfolio statistics ({target_asset})")

        # Fetch necessary market data.
        assets = chain(
            summary.starting_assets.keys(),
            Symbol_.iter_assets(p.symbol for p in summary.positions),
            [benchmark_asset],
        )
        prices = await self._prices.map_asset_prices(
            exchange=exchange,
            assets=assets,
            start=summary.start,
            end=Timestamp_.ceil(summary.end, interval),
            interval=interval,
            target_asset=target_asset,
        )

        return Statistics.compose(
            summary=summary,
            asset_prices=prices,
            interval=interval,
            benchmark_asset=benchmark_asset,
        )
