import logging
import operator
from collections import defaultdict
from decimal import Decimal
from typing import Callable, Dict, List, NamedTuple, Tuple

import numpy as np
import pandas as pd

from juno import Candle, Fill
from juno.math import floor_multiple
from juno.time import DAY_MS
from juno.utils import unpack_symbol

from .common import TradingSummary

Operator = Callable[[Decimal, Decimal], Decimal]

_log = logging.getLogger(__name__)


class Statistics(NamedTuple):
    performance: pd.Series
    a_returns: pd.Series
    g_returns: pd.Series
    neg_g_returns: pd.Series

    total_return: float
    annualized_return: float
    annualized_volatility: float
    annualized_downside_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    cagr: float


class PortfolioStatistics(NamedTuple):
    performance: pd.Series
    a_returns: pd.Series
    g_returns: pd.Series
    neg_g_returns: pd.Series

    total_return: float
    annualized_return: float
    annualized_volatility: float
    annualized_downside_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    cagr: float

    alpha: float
    beta: float


def get_benchmark_statistics(candles: List[Candle]) -> Statistics:
    performance = pd.Series([float(c.close) for c in candles])
    return _calculate_statistics(performance)


def get_portfolio_statistics(
    benchmark_stats: Statistics,
    base_fiat_candles: List[Candle],
    portfolio_candles: List[Candle],
    symbol: str,
    summary: TradingSummary
) -> PortfolioStatistics:
    start_day = floor_multiple(summary.start, DAY_MS)
    end_day = floor_multiple(summary.end, DAY_MS)
    length_days = (end_day - start_day) / DAY_MS
    base_asset, quote_asset = unpack_symbol(symbol)
    assert quote_asset == 'btc'  # TODO: We don't support other quote yet.
    assert len(base_fiat_candles) == length_days
    assert len(portfolio_candles) == length_days

    market_data = _get_market_data(symbol, base_fiat_candles, portfolio_candles)
    trades = _get_trades_from_summary(summary, symbol)
    asset_performance = _get_asset_performance(
        summary, symbol, start_day, end_day, market_data, trades
    )
    portfolio_performance = pd.Series(
        [float(sum(v for v in apd.values())) for apd in asset_performance.values()]
    )

    portfolio_stats = _calculate_statistics(portfolio_performance)
    return PortfolioStatistics(
        *portfolio_stats,
        *_get_alpha_beta(benchmark_stats, portfolio_stats),
    )


def _get_market_data(symbol: str, btc_fiat_daily: List[Candle], symbol_daily: List[Candle]):
    # Calculate fiat value for traded base assets.
    base_asset, quote_asset = unpack_symbol(symbol)
    market_data: Dict[str, Dict[int, Decimal]] = defaultdict(dict)
    for btc_fiat_candle, symbol_candle in zip(btc_fiat_daily, symbol_daily):
        time = btc_fiat_candle.time
        market_data['btc'][time] = btc_fiat_candle.close
        market_data[base_asset][time] = symbol_candle.close * btc_fiat_candle.close
    return market_data


def _get_trades_from_summary(
    summary: TradingSummary,
    symbol: str
) -> Dict[int, List[Tuple[str, Operator, Decimal]]]:
    base_asset, quote_asset = unpack_symbol(symbol)
    trades: Dict[int, List[Tuple[str, Operator, Decimal]]] = defaultdict(list)
    for pos in summary.positions:
        assert pos.closing_fills
        # Open.
        time = floor_multiple(pos.time, DAY_MS)
        day_trades = trades[time]
        day_trades.append((quote_asset, operator.sub, Fill.total_quote(pos.fills)))
        day_trades.append((
            base_asset,
            operator.add,
            Fill.total_size(pos.fills) - Fill.total_fee(pos.fills)
        ))
        # Close.
        time = floor_multiple(pos.closing_time, DAY_MS)
        day_trades = trades[time]
        day_trades.append((base_asset, operator.sub, Fill.total_size(pos.closing_fills)))
        day_trades.append((
            quote_asset,
            operator.add,
            Fill.total_quote(pos.closing_fills) - Fill.total_fee(pos.closing_fills)
        ))
    return trades


def _get_asset_performance(
    summary: TradingSummary,
    symbol: str,
    start_day: int,
    end_day: int,
    market_data: Dict[str, Dict[int, Decimal]],
    trades: Dict[int, List[Tuple[str, Operator, Decimal]]]
) -> Dict[int, Dict[str, Decimal]]:
    base_asset, quote_asset = unpack_symbol(symbol)

    asset_holdings: Dict[str, Decimal] = defaultdict(lambda: Decimal('0.0'))
    asset_holdings[quote_asset] = summary.quote

    asset_performance: Dict[int, Dict[str, Decimal]] = defaultdict(
        lambda: {k: Decimal('0.0') for k in market_data.keys()}
    )

    for time_day in range(start_day, end_day, DAY_MS):
        # Update holdings.
        day_trades = trades.get(time_day)
        if day_trades:
            for asset, op, size in day_trades:
                asset_holdings[asset] = op(asset_holdings[asset], size)

        # Update asset performance (mark-to-market portfolio).
        asset_performance_day = asset_performance[time_day]
        for asset in market_data.keys():
            asset_fiat_value = market_data[asset].get(time_day)
            if asset_fiat_value is not None:
                asset_performance_day[asset] = asset_holdings[asset] * asset_fiat_value
            else:  # Missing asset market data for the day.
                _log.warning('missing market data for day')
                # TODO: What if previous day also missing?? Maybe better to fill missing
                # candles?? Remove assert above.
                asset_performance_day[asset] = asset_performance[time_day - DAY_MS][asset]

    return asset_performance


def _calculate_statistics(performance: pd.Series) -> Statistics:
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

    return Statistics(
        performance=performance,
        a_returns=a_returns,
        g_returns=g_returns,
        neg_g_returns=neg_g_returns,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        annualized_downside_risk=annualized_downside_risk,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        cagr=cagr
    )


def _get_alpha_beta(
    benchmark_stats: Statistics, portfolio_stats: Statistics
) -> Tuple[float, float]:
    covariance_matrix = pd.concat(
        [portfolio_stats.g_returns, benchmark_stats.g_returns], axis=1
    ).dropna().cov()
    beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
    alpha = portfolio_stats.annualized_return - (beta * 365 * benchmark_stats.g_returns.mean())

    return alpha, beta
