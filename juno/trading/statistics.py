import asyncio
import logging
import operator
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Tuple

import numpy as np
import pandas as pd

from juno import Candle, Fill
from juno.asyncio import list_async
from juno.components import Chandler, Informant
from juno.math import floor_multiple
from juno.time import DAY_MS
from juno.utils import unpack_symbol

from .common import TradingSummary

Operator = Callable[[Decimal, Decimal], Decimal]

_log = logging.getLogger(__name__)


class AlphaBeta(NamedTuple):
    alpha: float
    beta: float


class Statistics(NamedTuple):
    performance: Any
    a_returns: Any
    g_returns: Any
    neg_g_returns: Any

    total_return: float
    annualized_return: float
    annualized_volatility: float
    annualized_downside_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    cagr: float


class Combined(NamedTuple):
    benchmark_stats: Statistics
    portfolio_stats: Statistics
    portfolio_alpha_beta: AlphaBeta


async def get_benchmark_statistics(
    chandler: Chandler, informant: Informant, start: int, end: int
) -> Statistics:
    start_day = floor_multiple(start, DAY_MS)
    end_day = floor_multiple(end, DAY_MS)

    # Find first exchange which supports the fiat pair.
    btc_fiat_symbol = 'btc-eur'
    btc_fiat_exchange = _find_first_exchange_for_symbol(informant, btc_fiat_symbol)

    btc_fiat_daily = await list_async(chandler.stream_candles(
        btc_fiat_exchange, btc_fiat_symbol, DAY_MS, start_day, end_day
    ))
    performance = pd.Series([float(c.close) for c in btc_fiat_daily])
    return _calculate_statistics(performance)


async def get_portfolio_statistics(
    chandler: Chandler,
    informant: Informant,
    exchange: str,
    symbol: str,
    summary: TradingSummary
) -> Statistics:
    start_day = floor_multiple(summary.start, DAY_MS)
    end_day = floor_multiple(summary.end, DAY_MS)
    length_days = (end_day - start_day) / DAY_MS
    base_asset, quote_asset = unpack_symbol(symbol)
    assert quote_asset == 'btc'  # TODO: We don't support other quote yet.

    # Find first exchange which supports the fiat pair.
    btc_fiat_symbol = 'btc-eur'
    btc_fiat_exchange = _find_first_exchange_for_symbol(informant, btc_fiat_symbol)

    # Fetch necessary market data.
    btc_fiat_daily, symbol_daily = await asyncio.gather(
        list_async(
            chandler.stream_candles(btc_fiat_exchange, btc_fiat_symbol, DAY_MS, start_day, end_day)
        ),
        list_async(chandler.stream_candles(exchange, symbol, DAY_MS, start_day, end_day)),
    )
    assert len(btc_fiat_daily) == length_days
    assert len(symbol_daily) == length_days

    market_data = _get_market_data(symbol, btc_fiat_daily, symbol_daily)
    trades = _get_trades_from_summary(summary, symbol)
    asset_performance = _get_asset_performance(
        summary, symbol, start_day, end_day, market_data, trades
    )
    portfolio_performance = pd.Series(
        [float(sum(v for v in apd.values())) for apd in asset_performance.values()]
    )

    return _calculate_statistics(portfolio_performance)


def get_alpha_beta(benchmark_stats: Statistics, portfolio_stats: Statistics) -> AlphaBeta:
    covariance_matrix = pd.concat(
        [portfolio_stats.g_returns, benchmark_stats.g_returns], axis=1
    ).dropna().cov()
    beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
    alpha = portfolio_stats.annualized_return - (beta * 365 * benchmark_stats.g_returns.mean())

    return AlphaBeta(alpha=alpha, beta=beta)


def _find_first_exchange_for_symbol(informant: Informant, symbol: str):
    for exchange in informant.list_exchanges():
        symbols = informant.list_symbols(exchange)
        if symbol in symbols:
            return exchange
    raise ValueError('Not found.')


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

    # Compute benchmark statistics.
    total_return = performance.iloc[-1] / performance.iloc[0] - 1
    annualized_return = 365 * g_returns.mean()
    annualized_volatility = np.sqrt(365) * g_returns.std()
    annualized_downside_risk = np.sqrt(365) * neg_g_returns.std()
    sharpe_ratio = annualized_return / annualized_volatility
    sortino_ratio = annualized_return / annualized_downside_risk
    cagr = (
        (performance.iloc[-1] / performance.iloc[0]) **
        (1 / (performance.size / 365))
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
