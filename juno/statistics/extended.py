from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable, NamedTuple

import numpy as np
import pandas as pd

from juno import Interval
from juno.math import floor_multiple
from juno.time import DAY_MS
from juno.trading import TradingSummary
from juno.utils import unpack_assets

Operator = Callable[[Decimal, Decimal], Decimal]
_SQRT_365 = np.sqrt(365)


class ExtendedStatistics(NamedTuple):
    total_return: float
    annualized_return: float
    annualized_volatility: float
    annualized_downside_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    cagr: float

    alpha: float = 0.0
    beta: float = 0.0

    @staticmethod
    def compose(
        summary: TradingSummary,
        asset_prices: dict[str, list[Decimal]],
        interval: Interval = DAY_MS,
        benchmark_asset: str = "btc",
    ) -> ExtendedStatistics:
        assert summary.end is not None

        start = floor_multiple(summary.start, interval)
        end = floor_multiple(summary.end, interval)

        # Validate we have enough data. It may be that trading ended prematurely and we have more
        # price points available than needed.
        num_ticks = (end - start) // interval
        for asset, prices in asset_prices.items():
            if len(prices) < num_ticks:
                raise ValueError(
                    f"Expected at least {num_ticks} price points for {asset} but got {len(prices)}"
                )

        trades = _get_trades_from_summary(summary, interval)
        asset_performance = _get_asset_performance(
            summary, start, end, asset_prices, trades, interval
        )
        portfolio_performance = pd.Series(
            [float(sum(v for v in apd.values())) for apd in asset_performance]
        )
        benchmark_performance = pd.Series([float(p) for p in asset_prices[benchmark_asset]])

        return _calculate_statistics(portfolio_performance, benchmark_performance)


def _get_trades_from_summary(
    summary: TradingSummary, interval: int
) -> dict[int, list[tuple[str, Decimal]]]:
    trades: dict[int, list[tuple[str, Decimal]]] = defaultdict(list)
    for pos in summary.positions:
        base_asset, quote_asset = unpack_assets(pos.symbol)
        # Open.
        time = floor_multiple(pos.open_time, interval)
        day_trades = trades[time]
        day_trades.append((quote_asset, -pos.cost))
        day_trades.append((base_asset, +pos.base_gain))
        # Close.
        time = floor_multiple(pos.close_time, interval)
        day_trades = trades[time]
        day_trades.append((base_asset, -pos.base_cost))
        day_trades.append((quote_asset, +pos.gain))
    return trades


def _get_asset_performance(
    summary: TradingSummary,
    start_day: int,
    end_day: int,
    asset_prices: dict[str, list[Decimal]],
    trades: dict[int, list[tuple[str, Decimal]]],
    interval: int,
) -> list[dict[str, Decimal]]:
    asset_holdings: dict[str, Decimal] = defaultdict(lambda: Decimal("0.0"))
    asset_holdings.update(summary.starting_assets)

    asset_performances: list[dict[str, Decimal]] = []

    asset_performances.append(
        _get_asset_performances_from_holdings(asset_holdings, asset_prices, 0)
    )

    # Offset the open price, hence enumrate starting from 1.
    for price_i, time_day in enumerate(range(start_day, end_day, interval), 1):
        # Update holdings.
        day_trades = trades.get(time_day)
        if day_trades:
            for asset, size in day_trades:
                asset_holdings[asset] = asset_holdings[asset] + size

        # Update asset performance (mark-to-market portfolio).
        asset_performances.append(
            _get_asset_performances_from_holdings(asset_holdings, asset_prices, price_i)
        )

    return asset_performances


def _get_asset_performances_from_holdings(
    asset_holdings: dict[str, Decimal], asset_prices: dict[str, list[Decimal]], price_i: int
) -> dict[str, Decimal]:
    asset_performance = {k: Decimal("0.0") for k in asset_prices.keys()}
    for asset, prices in asset_prices.items():
        asset_performance[asset] = asset_holdings[asset] * prices[price_i]
    return asset_performance


def _get_g_returns(performance: pd.Series) -> Any:
    a_returns = performance.pct_change().dropna()
    return np.log(a_returns + 1)


def _calculate_statistics(
    performance: pd.Series, benchmark_performance: pd.Series
) -> ExtendedStatistics:
    g_returns = _get_g_returns(performance)
    neg_g_returns = g_returns[g_returns < 0].dropna()
    benchmark_g_returns = _get_g_returns(benchmark_performance)

    # Compute statistics.
    total_return = performance.iloc[-1] / performance.iloc[0] - 1
    annualized_return = 365 * g_returns.mean()
    annualized_volatility = _SQRT_365 * g_returns.std(ddof=0)
    annualized_downside_risk = _SQRT_365 * neg_g_returns.std(ddof=0)

    sharpe_ratio = (
        annualized_return / annualized_volatility if annualized_volatility else Decimal("0.0")
    )
    sortino_ratio = (
        annualized_return / annualized_downside_risk
        if annualized_downside_risk
        else Decimal("0.0")
    )
    cagr = ((performance.iloc[-1] / performance.iloc[0]) ** (1 / (performance.size / 365))) - 1

    # If benchmark provided, calculate alpha and beta.
    alpha, beta = 0.0, 0.0
    covariance_matrix = pd.concat([g_returns, benchmark_g_returns], axis=1).dropna().cov(ddof=0)
    y = covariance_matrix.iloc[1].iloc[1]
    if y != 0:
        x = covariance_matrix.iloc[0].iloc[1]
        beta = x / y
        alpha = annualized_return - (beta * 365 * benchmark_g_returns.mean())

    return ExtendedStatistics(
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        annualized_downside_risk=annualized_downside_risk,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        cagr=cagr,
        alpha=alpha,
        beta=beta,
    )
