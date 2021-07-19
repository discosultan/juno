from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from juno import Interval
from juno.time import DAY_MS
from juno.trading import TradingSummary

from .core import CoreStatistics
from .extended import ExtendedStatistics


@dataclass
class Statistics:
    core: CoreStatistics
    extended: ExtendedStatistics

    @staticmethod
    def compose(
        summary: TradingSummary,
        asset_prices: dict[str, list[Decimal]],
        interval: Interval = DAY_MS,
        benchmark_asset: str = "btc",
    ) -> Statistics:
        return Statistics(
            core=CoreStatistics.compose(summary),
            extended=ExtendedStatistics.compose(
                summary=summary,
                asset_prices=asset_prices,
                interval=interval,
                benchmark_asset=benchmark_asset,
            ),
        )
