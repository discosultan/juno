import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from juno.asyncio import list_async
from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.strategies import MA, MAMACX
from juno.time import DAY_MS, HOUR_MS, strptimestamp
from juno.trading import MissedCandlePolicy, Trader
from juno.utils import unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = HOUR_MS

Operator = Callable[[Decimal, Decimal], Decimal]


async def main() -> None:
    sqlite = SQLite()
    config = from_env()
    binance = init_instance(Binance, config)
    coinbase = init_instance(Coinbase, config)
    chandler = Chandler(
        Trades(sqlite, [binance, coinbase]),
        sqlite,
        [binance, coinbase]
    )
    informant = Informant(sqlite, [binance, coinbase])
    start = floor_multiple(strptimestamp('2019-01-01'), INTERVAL)
    end = floor_multiple(strptimestamp('2019-12-01'), INTERVAL)
    base_asset, quote_asset = unpack_symbol(SYMBOL)
    async with binance, coinbase, informant:
        trader = Trader(
            chandler=chandler,
            informant=informant,
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=Decimal('1.0'),
            new_strategy=lambda: MAMACX(3, 73, Decimal('-0.102'), Decimal('0.239'), 4, MA.SMA,
                                        MA.SMMA),
            trailing_stop=Decimal('0.0827'),
            missed_candle_policy=MissedCandlePolicy.LAST
        )
        await trader.run()

        start_day = floor_multiple(start, DAY_MS)
        end_day = floor_multiple(end, DAY_MS)
        length_days = (end_day - start_day) / DAY_MS
        # 1. Assumes symbol quote is BTC.
        # 2. We run it after trading step, because it might use the same candle configuration which
        # we don't support processing concurrently.

        assert quote_asset == 'btc'  # TODO: Don't support others yet.

        btc_fiat_daily, symbol_daily = await asyncio.gather(
            list_async(chandler.stream_candles('coinbase', 'btc-eur', DAY_MS, start_day, end_day)),
            list_async(chandler.stream_candles('binance', SYMBOL, DAY_MS, start_day, end_day)),
        )
        assert len(btc_fiat_daily) == length_days
        assert len(symbol_daily) == length_days
        market_data: Dict[str, Dict[int, Decimal]] = defaultdict(dict)
        for btc_fiat_candle, symbol_candle in zip(btc_fiat_daily, symbol_daily):
            time = btc_fiat_candle.time
            market_data['btc'][time] = btc_fiat_candle.close
            market_data[base_asset][time] = symbol_candle.close * btc_fiat_candle.close

        trades: Dict[int, List[Tuple[str, Decimal]]] = defaultdict(list)
        for pos in trader.summary.positions:
            assert pos.closing_fills
            # Open.
            time = floor_multiple(pos.time, DAY_MS)
            day_trades = trades[time]
            day_trades.append((quote_asset, -pos.cost))
            day_trades.append((base_asset, +pos.base_gain))
            # Close.
            time = floor_multiple(pos.closing_time, DAY_MS)
            day_trades = trades[time]
            day_trades.append((base_asset, -pos.base_cost))
            day_trades.append((quote_asset, +pos.gain))

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
                for asset, size in day_trades2:
                    asset_holdings[asset] = asset_holdings[asset] + size

            # Update asset performance (mark-to-market portfolio).
            asset_performance_day = asset_performance[time_day]
            for asset in market_data.keys():
                asset_fiat_value = market_data[asset].get(time_day)
                if asset_fiat_value is not None:
                    asset_performance_day[asset] = asset_holdings[asset] * asset_fiat_value
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

        benchmark_performance = pd.Series([float(c.close) for c in btc_fiat_daily])
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
            (benchmark_performance.iloc[-1] / benchmark_performance.iloc[0])
            ** (1 / (length_days / 365))
        ) - 1

        # Compute portfolio statistics.
        portfolio_total_return = portfolio_performance.iloc[-1] / portfolio_performance.iloc[0] - 1
        portfolio_annualized_return = 365 * portfolio_g_returns.mean()
        portfolio_annualized_volatility = np.sqrt(365) * portfolio_g_returns.std()
        portfolio_annualized_downside_risk = np.sqrt(365) * portfolio_neg_g_returns.std()
        portfolio_sharpe_ratio = portfolio_annualized_return / portfolio_annualized_volatility
        portfolio_sortino_ratio = portfolio_annualized_return / portfolio_annualized_downside_risk
        portfolio_cagr = (
            (portfolio_performance.iloc[-1] / portfolio_performance.iloc[0])
            ** (1 / (length_days / 365))
        ) - 1
        covariance_matrix = pd.concat(
            [portfolio_g_returns, benchmark_g_returns], axis=1
        ).dropna().cov()
        beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
        alpha = portfolio_annualized_return - (beta * 365 * benchmark_g_returns.mean())

        logging.info(f'{benchmark_total_return=}')
        logging.info(f'{benchmark_annualized_return=}')
        logging.info(f'{benchmark_annualized_volatility=}')
        logging.info(f'{benchmark_annualized_downside_risk=}')
        logging.info(f'{benchmark_sharpe_ratio=}')
        logging.info(f'{benchmark_sortino_ratio=}')
        logging.info(f'{benchmark_cagr=}')

        logging.info(f'{portfolio_total_return=}')
        logging.info(f'{portfolio_annualized_return=}')
        logging.info(f'{portfolio_annualized_volatility=}')
        logging.info(f'{portfolio_annualized_downside_risk=}')
        logging.info(f'{portfolio_sharpe_ratio=}')
        logging.info(f'{portfolio_sortino_ratio=}')
        logging.info(f'{portfolio_cagr=}')
        logging.info(f'{alpha=}')
        logging.info(f'{beta=}')

    logging.info('done')


asyncio.run(main())
