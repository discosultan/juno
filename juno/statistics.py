import logging
from collections import defaultdict
from decimal import Decimal
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

import numpy as np
import pandas as pd

from juno.math import floor_multiple
from juno.time import DAY_MS
from juno.utils import unpack_symbol

from .trading import TradingSummary

Operator = Callable[[Decimal, Decimal], Decimal]

_log = logging.getLogger(__name__)


class Statistics(NamedTuple):
    total_return: float
    annualized_return: float
    annualized_volatility: float
    annualized_downside_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    cagr: float

    alpha: float = 0.0
    beta: float = 0.0


class AnalysisSummary(NamedTuple):
    performance: pd.Series
    a_returns: pd.Series
    g_returns: pd.Series
    neg_g_returns: pd.Series

    stats: Statistics


def analyse_benchmark(prices: List[Decimal]) -> AnalysisSummary:
    performance = pd.Series([float(p) for p in prices])
    _log.info('calculating benchmark statistics')
    return _calculate_statistics(performance)


def analyse_portfolio(
    benchmark_g_returns: pd.Series,
    fiat_daily_prices: Dict[str, List[Decimal]],
    trading_summary: TradingSummary,
    interval: int = DAY_MS,
) -> AnalysisSummary:
    assert trading_summary.end is not None

    start_day = floor_multiple(trading_summary.start, interval)
    end_day = floor_multiple(trading_summary.end, interval)

    # Validate we have enough data.
    num_days = (end_day - start_day) // interval
    for asset, prices in fiat_daily_prices.items():
        if len(prices) != num_days:
            raise ValueError(
                f'Expected {num_days} price points for {asset} but got {len(prices)}'
            )

    trades = _get_trades_from_summary(trading_summary, interval)
    asset_performance = _get_asset_performance(
        trading_summary, start_day, end_day, fiat_daily_prices, trades, interval
    )
    portfolio_performance = pd.Series(
        [float(sum(v for v in apd.values())) for apd in asset_performance]
    )

    _log.info('calculating portfolio statistics')
    return _calculate_statistics(portfolio_performance, benchmark_g_returns)


def _get_trades_from_summary(
    summary: TradingSummary, interval: int
) -> Dict[int, List[Tuple[str, Decimal]]]:
    trades: Dict[int, List[Tuple[str, Decimal]]] = defaultdict(list)
    for pos in summary.get_positions():
        base_asset, quote_asset = unpack_symbol(pos.symbol)
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
    market_data: Dict[str, List[Decimal]],
    trades: Dict[int, List[Tuple[str, Decimal]]],
    interval: int,
) -> List[Dict[str, Decimal]]:
    asset_holdings: Dict[str, Decimal] = defaultdict(lambda: Decimal('0.0'))
    asset_holdings[summary.quote_asset] = summary.quote

    asset_performance: List[Dict[str, Decimal]] = []

    i = 0
    for time_day in range(start_day, end_day, interval):
        # Update holdings.
        day_trades = trades.get(time_day)
        if day_trades:
            for asset, size in day_trades:
                asset_holdings[asset] = asset_holdings[asset] + size

        # Update asset performance (mark-to-market portfolio).
        asset_performance_day = {k: Decimal('0.0') for k in market_data.keys()}
        for asset, asset_prices in market_data.items():
            asset_performance_day[asset] = asset_holdings[asset] * asset_prices[i]

        asset_performance.append(asset_performance_day)
        i += 1

    return asset_performance


def _calculate_statistics(
    performance: pd.Series, benchmark_g_returns: Optional[pd.Series] = None
) -> AnalysisSummary:
    a_returns = performance.pct_change().dropna()
    g_returns = np.log(a_returns + 1)
    neg_g_returns = g_returns[g_returns < 0].dropna()

    # Compute statistics.
    total_return = performance.iloc[-1] / performance.iloc[0] - 1
    annualized_return = 365 * g_returns.mean()
    annualized_volatility = np.sqrt(365) * g_returns.std()
    annualized_downside_risk = np.sqrt(365) * neg_g_returns.std()
    sharpe_ratio = annualized_return / annualized_volatility
    sortino_ratio = annualized_return / annualized_downside_risk
    cagr = (
        (performance.iloc[-1] / performance.iloc[0])
        ** (1 / (performance.size / 365))
    ) - 1

    # If benchmark provided, calculate alpha and beta.
    alpha, beta = 0.0, 0.0
    if benchmark_g_returns is not None:
        covariance_matrix = pd.concat(
            [g_returns, benchmark_g_returns], axis=1
        ).dropna().cov()
        beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
        alpha = annualized_return - (beta * 365 * benchmark_g_returns.mean())

    return AnalysisSummary(
        performance=performance,
        a_returns=a_returns,
        g_returns=g_returns,
        neg_g_returns=neg_g_returns,
        stats=Statistics(
            total_return=total_return,
            annualized_return=annualized_return,
            annualized_volatility=annualized_volatility,
            annualized_downside_risk=annualized_downside_risk,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            cagr=cagr,
            alpha=alpha,
            beta=beta
        )
    )
