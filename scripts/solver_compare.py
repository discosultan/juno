import asyncio
import logging
from decimal import Decimal

from juno import MissedCandlePolicy, components, exchanges, storages, strategies, time
from juno.config import format_as_config, from_env, get_module_type_constructor, init_instance
from juno.math import floor_multiple
from juno.solvers import Python, Rust, Solver
from juno.statistics import analyse_benchmark, analyse_portfolio
from juno.traders import Basic
from juno.utils import extract_public, unpack_symbol

# SYMBOL = 'eth-btc'
# INTERVAL = time.HOUR_MS
# START = time.strptimestamp('2018-09-15')
# END = time.strptimestamp('2020-04-01')
# MISSED_CANDLE_POLICY = MissedCandlePolicy.RESTART
# TRAILING_STOP = Decimal('0.3772')

# SHORT_PERIOD = 15
# LONG_PERIOD = 22
# NEG_THRESHOLD = Decimal('-0.375')
# POS_THRESHOLD = Decimal('0.481')
# PERSISTENCE = 1
# SHORT_MA = 'smma'
# LONG_MA = 'kama'

# Triggered closing and opening long position on same tick with trailing stop.
SYMBOL = 'eth-btc'
INTERVAL = time.HOUR_MS
START = time.strptimestamp('2019-06-19')
END = time.strptimestamp('2019-06-23')
MISSED_CANDLE_POLICY = MissedCandlePolicy.IGNORE
TRAILING_STOP = Decimal('0.044')
TAKE_PROFIT = Decimal('0.0')
LONG = False
SHORT = True

SHORT_PERIOD = 4
LONG_PERIOD = 60
NEG_THRESHOLD = Decimal('-0.435')
POS_THRESHOLD = Decimal('0.211')
PERSISTENCE = 5
SHORT_MA = 'kama'
LONG_MA = 'sma'

# SYMBOL = 'eth-btc'
# INTERVAL = time.HOUR_MS
# START = time.strptimestamp('2017-07-14')
# END = time.strptimestamp('2019-12-07')
# MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
# TRAILING_STOP = Decimal('0.8486')

# SHORT_PERIOD = 7
# LONG_PERIOD = 49
# NEG_THRESHOLD = Decimal('-0.946')
# POS_THRESHOLD = Decimal('0.854')
# PERSISTENCE = 6
# SHORT_MA = 'smma'
# LONG_MA = 'sma'

# SYMBOL = 'enj-bnb'  # NB! Non-btc quote not supported in prices!
# INTERVAL = time.DAY_MS
# START = time.strptimestamp('2019-01-01')
# END = time.strptimestamp('2019-12-22')
# MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
# TRAILING_STOP = Decimal('0.0')

# SHORT_PERIOD = 1
# LONG_PERIOD = 8
# NEG_THRESHOLD = Decimal('-0.624')
# POS_THRESHOLD = Decimal('0.893')
# PERSISTENCE = 2
# SHORT_MA = 'smma'
# LONG_MA = 'smma'


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
        fiat_prices = await prices.map_prices(
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
            strategy_type=strategies.MAMACX,
            start=start,
            end=end,
            quote=Decimal('1.0'),
            candles=candles,
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            missed_candle_policy=MISSED_CANDLE_POLICY,
            trailing_stop=TRAILING_STOP,
            take_profit=TAKE_PROFIT,
            long=LONG,
            short=SHORT,
            strategy_args=(
                SHORT_PERIOD,
                LONG_PERIOD,
                NEG_THRESHOLD,
                POS_THRESHOLD,
                PERSISTENCE,
                SHORT_MA,
                LONG_MA,
            ),
        )
        rust_result = rust_solver.solve(solver_config)
        python_result = python_solver.solve(solver_config)

        trading_summary = await trader.run(Basic.Config(
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=Decimal('1.0'),
            strategy=get_module_type_constructor(
                strategies,
                {
                    'type': 'mamacx',
                    'short_period': SHORT_PERIOD,
                    'long_period': LONG_PERIOD,
                    'neg_threshold': NEG_THRESHOLD,
                    'pos_threshold': POS_THRESHOLD,
                    'persistence': PERSISTENCE,
                    'short_ma': SHORT_MA,
                    'long_ma': LONG_MA,
                },
            ),
            missed_candle_policy=MISSED_CANDLE_POLICY,
            trailing_stop=TRAILING_STOP,
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
        logging.info(f'alpha {rust_result.alpha}')
        # logging.info(f'profit {rust_result.profit}')
        # logging.info(f'mean pos dur {rust_result.mean_position_duration}')

        logging.info('=== python solver ===')
        logging.info(f'alpha {python_result.alpha}')
        # logging.info(f'profit {python_result.profit}')
        # logging.info(f'mean pos dur {python_result.mean_position_duration}')

        logging.info('=== python trader ===')
        logging.info(f'alpha {portfolio.stats.alpha}')
        logging.info(f'profit {trading_summary.profit}')
        logging.info(f'mean pos dur {trading_summary.mean_position_duration}')
        logging.info(f'{format_as_config(extract_public(trading_summary))}')


asyncio.run(main())
