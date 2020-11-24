import asyncio
import logging
from decimal import Decimal

from juno import MissedCandlePolicy, components, exchanges, storages, strategies, time
from juno.config import format_as_config, from_env, init_instance
from juno.math import floor_multiple
from juno.solvers import Python, Rust, Solver
from juno.statistics import analyse_benchmark, analyse_portfolio
from juno.traders import Basic, BasicConfig
from juno.typing import TypeConstructor
from juno.utils import extract_public, unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = time.DAY_MS
START = time.strptimestamp('2020-03-10')
END = time.strptimestamp('2020-04-20')
MISSED_CANDLE_POLICY = MissedCandlePolicy.RESTART
STOP_LOSS = Decimal('0.0')
TRAIL_STOP_LOSS = True
TAKE_PROFIT = Decimal('0.0')
LONG = True
SHORT = True
STRATEGY_TYPE = strategies.Macd
# NB! Needs to be ordered!
STRATEGY_KWARGS = {
    'short_period': 1,
    'long_period': 16,
    'signal_period': 23,
    'persistence': 0,
}


async def main() -> None:
    start = floor_multiple(START, INTERVAL)
    end = floor_multiple(END, INTERVAL)
    base_asset, quote_asset = unpack_symbol(SYMBOL)

    storage = storages.SQLite()
    binance = init_instance(exchanges.Binance, from_env())
    exchange_list = [binance]
    informant = components.Informant(storage, exchange_list)
    trades = components.Trades(storage, exchange_list)
    chandler = components.Chandler(trades=trades, storage=storage, exchanges=exchange_list)
    prices = components.Prices(chandler=chandler)
    trader = Basic(chandler=chandler, informant=informant, exchanges=exchange_list)
    rust_solver = Rust(informant=informant)
    python_solver = Python(informant=informant)
    async with binance, informant, rust_solver:
        candles = await chandler.list_candles('binance', SYMBOL, INTERVAL, start, end)
        fiat_prices = await prices.map_asset_prices(
            exchange='binance',
            symbols=[SYMBOL],
            start=start,
            end=end,
        )
        benchmark = analyse_benchmark(fiat_prices['btc'])

        logging.info('running backtest in rust solver, python solver, python trader ...')

        solver_config = Solver.Config(
            fiat_prices=fiat_prices,
            benchmark_g_returns=benchmark.g_returns,
            strategy_type=STRATEGY_TYPE,
            strategy_args=tuple(STRATEGY_KWARGS.values()),
            start=start,
            end=end,
            quote=Decimal('1.0'),
            candles=candles,
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            missed_candle_policy=MISSED_CANDLE_POLICY,
            stop_loss=STOP_LOSS,
            trail_stop_loss=TRAIL_STOP_LOSS,
            take_profit=TAKE_PROFIT,
            long=LONG,
            short=SHORT,
        )
        rust_result = rust_solver.solve(solver_config)
        python_result = python_solver.solve(solver_config)

        trader_state = await trader.initialize(BasicConfig(
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=Decimal('1.0'),
            strategy=TypeConstructor.from_type(STRATEGY_TYPE, **STRATEGY_KWARGS),
            missed_candle_policy=MISSED_CANDLE_POLICY,
            stop_loss=STOP_LOSS,
            take_profit=TAKE_PROFIT,
            adjust_start=False,
            long=LONG,
            short=SHORT,
        ))
        trading_summary = await trader.run(trader_state)
        portfolio = analyse_portfolio(
            benchmark_g_returns=benchmark.g_returns,
            asset_prices=fiat_prices,
            trading_summary=trading_summary,
        )

        logging.info('=== rust solver ===')
        # logging.info(f'alpha {rust_result.alpha}')
        logging.info(f'sharpe ratio {rust_result.sharpe_ratio}')
        # logging.info(f'profit {rust_result.profit}')
        # logging.info(f'mean pos dur {rust_result.mean_position_duration}')

        logging.info('=== python solver ===')
        # logging.info(f'alpha {python_result.alpha}')
        logging.info(f'sharpe ratio {python_result.sharpe_ratio}')
        # logging.info(f'profit {python_result.profit}')
        # logging.info(f'mean pos dur {python_result.mean_position_duration}')

        logging.info('=== python trader ===')
        # logging.info(f'alpha {portfolio.stats.alpha}')
        logging.info(f'sharpe ratio {portfolio.stats.sharpe_ratio}')
        logging.info(f'profit {trading_summary.profit}')
        logging.info(f'mean pos dur {trading_summary.mean_position_duration}')
        logging.info(f'{format_as_config(extract_public(trading_summary))}')


asyncio.run(main())
