import asyncio
import logging
from decimal import Decimal

from juno import MissedCandlePolicy, components, exchanges, storages, strategies, time
from juno.config import format_as_config, from_env, init_instance
from juno.math import floor_multiple
from juno.solvers import Individual, Python, Rust, Solver
from juno.statistics import analyse_benchmark, analyse_portfolio
# from juno.strategies import MidTrendPolicy
from juno.traders import Basic
from juno.typing import TypeConstructor
from juno.utils import extract_public, unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = time.DAY_MS
START = time.strptimestamp('2017-08-17')
END = time.strptimestamp('2017-10-01')
MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
STOP_LOSS = Decimal('0.124')
TRAIL_STOP_LOSS = True
TAKE_PROFIT = Decimal('0.0')
LONG = False
SHORT = True
# STRATEGY_TYPE = strategies.FourWeekRule
# STRATEGY_KWARGS = {
#     'period': 28,
#     'ma': 'smma',
#     'ma_period': 14,
#     'mid_trend_policy': MidTrendPolicy.IGNORE,
# }
STRATEGY_TYPE = strategies.MAMACX
STRATEGY_KWARGS = {
    'short_period': 4,
    'long_period': 60,
    'neg_threshold': Decimal('-0.435'),
    'pos_threshold': Decimal('0.211'),
    'persistence': 5,
    'short_ma': 'kama',
    'long_ma': 'sma',
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
            start=start,
            end=end,
            quote=Decimal('1.0'),
            candles={(SYMBOL, INTERVAL): candles},
            exchange='binance',
        )
        individual = Individual((
            SYMBOL,  # symbol
            INTERVAL,  # interval
            MISSED_CANDLE_POLICY,  # missed_candle_policy
            STOP_LOSS,  # stop_loss
            TRAIL_STOP_LOSS,  # trail_stop_loss
            TAKE_PROFIT,  # take_profit
            LONG,  # long
            SHORT,  # short
            *STRATEGY_KWARGS.values(),  # strategy_args
        ))
        [rust_fitness] = rust_solver.solve(solver_config, [individual])
        [python_fitness] = python_solver.solve(solver_config, [individual])

        trading_summary = await trader.run(Basic.Config(
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
        portfolio = analyse_portfolio(
            benchmark_g_returns=benchmark.g_returns,
            fiat_prices=fiat_prices,
            trading_summary=trading_summary,
        )

        logging.info('=== rust solver ===')
        # logging.info(f'alpha {rust_fitness.alpha}')
        logging.info(f'sharpe ratio {rust_fitness.sharpe_ratio}')
        # logging.info(f'profit {rust_fitness.profit}')
        # logging.info(f'mean pos dur {rust_fitness.mean_position_duration}')

        logging.info('=== python solver ===')
        # logging.info(f'alpha {python_fitness.alpha}')
        logging.info(f'sharpe ratio {python_fitness.sharpe_ratio}')
        # logging.info(f'profit {python_fitness.profit}')
        # logging.info(f'mean pos dur {python_fitness.mean_position_duration}')

        logging.info('=== python trader ===')
        # logging.info(f'alpha {portfolio.stats.alpha}')
        logging.info(f'sharpe ratio {portfolio.stats.sharpe_ratio}')
        logging.info(f'profit {trading_summary.profit}')
        logging.info(f'mean pos dur {trading_summary.mean_position_duration}')
        logging.info(f'{format_as_config(extract_public(trading_summary))}')


asyncio.run(main())
