import asyncio
import operator
from collections import defaultdict
from decimal import Decimal
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from juno import Fill
from juno.asyncio import list_async
from juno.components import Chandler, Informant
from juno.math import floor_multiple
from juno.time import DAY_MS
from juno.utils import unpack_symbol
from . import TradingSummary

Operator = Callable[[Decimal, Decimal], Decimal]


async def analyze(
    chandler: Chandler,
    informant: Informant,
    exchange: str,
    symbol: str,
    summary: TradingSummary
):
    start_day = floor_multiple(summary.start, DAY_MS)
    end_day = floor_multiple(summary.end, DAY_MS)
    length_days = (end_day - start_day) / DAY_MS
    base_asset, quote_asset = unpack_symbol(symbol)
    assert quote_asset == 'btc'  # TODO: We don't support other quote yet.

    # Find first exchange which supports the fiat pair.
    btc_fiat_symbol = 'btc-eur'
    btc_fiat_exchange = find_first_exchange_for_symbol(informant, btc_fiat_symbol)

    # Fetch necessary market data.
    btc_fiat_daily, symbol_daily = await asyncio.gather(
        list_async(
            chandler.stream_candles(btc_fiat_symbol, btc_fiat_exchange, DAY_MS, start_day, end_day)
        ),
        list_async(chandler.stream_candles(exchange, symbol, DAY_MS, start_day, end_day)),
    )
    assert len(btc_fiat_daily) == length_days
    assert len(symbol_daily) == length_days

    # Calculate fiat value for traded base assets.
    market_data: Dict[str, Dict[int, Decimal]] = defaultdict(dict)
    for btc_fiat_candle, symbol_candle in zip(btc_fiat_daily, symbol_daily):
        time = btc_fiat_candle.time
        market_data['btc'][time] = btc_fiat_candle.close
        market_data[base_asset][time] = symbol_candle.close * btc_fiat_candle.close

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

    asset_holdings: Dict[str, Decimal] = defaultdict(lambda: Decimal('0.0'))
    asset_holdings[quote_asset] = trader.summary.quote

    asset_performance: Dict[int, Dict[str, Decimal]] = defaultdict(
        lambda: {k: Decimal('0.0') for k in market_data.keys()}
    )

    for time_day in range(start_day, end_day, DAY_MS):
        # Update holdings.
        # TODO: Improve naming.
        day_trades2 = trades.get(time_day)
        if day_trades2:
            for asset, op, size in day_trades2:
                asset_holdings[asset] = op(asset_holdings[asset], size)

        # Update asset performance (mark-to-market portfolio).
        asset_performance_day = asset_performance[time_day]
        for asset in market_data.keys():
            asset_eur_value = market_data[asset].get(time_day)
            if asset_eur_value is not None:
                asset_performance_day[asset] = asset_holdings[asset] * asset_eur_value
            else:  # Missing asset market data for the day.
                logging.warning('missing market data for day')
                # TODO: What if previous day also missing?? Maybe better to fill missing
                # candles?? Remove assert above.
                asset_performance_day[asset] = asset_performance[time_day - DAY_MS][asset]

    # Update portfolio performance.
    portfolio_performance = pd.Series(
        [float(sum(v for v in apd.values())) for apd in asset_performance.values()]
    )
    portfolio_a_returns = portfolio_performance.pct_change().dropna()
    portfolio_g_returns = np.log(portfolio_a_returns + 1)
    portfolio_neg_g_returns = portfolio_g_returns[portfolio_g_returns < 0].dropna()

    benchmark_performance = pd.Series([float(c.close) for c in btc_eur_daily])
    benchmark_a_returns = benchmark_performance.pct_change().dropna()
    benchmark_g_returns = np.log(benchmark_a_returns + 1)
    benchmark_neg_g_returns = benchmark_g_returns[benchmark_g_returns < 0].dropna()

    # Compute benchmark statistics.
    benchmark_total_return = benchmark_performance.iloc[-1] / benchmark_performance.iloc[0] - 1
    benchmark_annualized_return = 365 * benchmark_g_returns.mean()
    benchmark_annualized_volatility = np.sqrt(365) * benchmark_g_returns.std()
    benchmark_annualized_downside_risk = np.sqrt(365) * benchmark_neg_g_returns.std()
    benchmark_sharpe_ratio = benchmark_annualized_return / benchmark_annualized_volatility
    benchmark_sortino_ratio = benchmark_annualized_return / benchmark_annualized_downside_risk
    benchmark_cagr = (
        (benchmark_performance.iloc[-1] / benchmark_performance.iloc[0]) **
        (1 / (length_days / 365))
    ) - 1

    # Compute portfolio statistics.
    portfolio_total_return = portfolio_performance.iloc[-1] / portfolio_performance.iloc[0] - 1
    portfolio_annualized_return = 365 * portfolio_g_returns.mean()
    portfolio_annualized_volatility = np.sqrt(365) * portfolio_g_returns.std()
    portfolio_annualized_downside_risk = np.sqrt(365) * portfolio_neg_g_returns.std()
    portfolio_sharpe_ratio = portfolio_annualized_return / portfolio_annualized_volatility
    portfolio_sortino_ratio = portfolio_annualized_return / portfolio_annualized_downside_risk
    portfolio_cagr = (
        (portfolio_performance.iloc[-1] / portfolio_performance.iloc[0]) **
        (1 / (length_days / 365))
    ) - 1
    covariance_matrix = pd.concat(
        [portfolio_g_returns, benchmark_g_returns], axis=1
    ).dropna().cov()
    beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
    alpha = portfolio_annualized_return - (beta * 365 * benchmark_g_returns.mean())


def find_first_exchange_for_symbol(informant: Informant, symbol: str):
    for exchange in informant.list_exchanges():
        symbols = informant.list_symbols(exchange)
        if btc_fiat_symbol in symbols:
            return exchange
    raise ValueError('Not found.')
