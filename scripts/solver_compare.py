import asyncio
import logging
from decimal import Decimal

from juno import components, exchanges, optimization, storages, strategies, time
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.strategies import MA
from juno.trading import (
    MissedCandlePolicy, Trader, get_benchmark_statistics, get_portfolio_statistics
)
from juno.utils import unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = time.HOUR_MS
START = time.strptimestamp('2017-07-14')
END = time.strptimestamp('2019-12-07')
MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
TRAILING_STOP = Decimal('0.8486')

SHORT_PERIOD = 7
LONG_PERIOD = 49
NEG_THRESHOLD = Decimal('-0.946')
POS_THRESHOLD = Decimal('0.854')
PERSISTENCE = 6
SHORT_MA = MA.SMMA
LONG_MA = MA.SMA

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
# SHORT_MA = MA.SMMA
# LONG_MA = MA.SMMA


async def main() -> None:
    start = floor_multiple(START, INTERVAL)
    end = floor_multiple(END, INTERVAL)

    storage = storages.SQLite()
    binance = init_instance(exchanges.Binance, from_env())
    coinbase = init_instance(exchanges.Coinbase, from_env())
    exchange_list = [binance, coinbase]
    informant = components.Informant(storage, exchange_list)
    trades = components.Trades(storage, exchange_list)
    chandler = components.Chandler(trades=trades, storage=storage, exchanges=exchange_list)
    prices = components.Prices(chandler)
    rust_solver = optimization.Rust()
    python_solver = optimization.Python()
    async with binance, coinbase, informant, rust_solver:
        candles = await chandler.list_candles('binance', SYMBOL, INTERVAL, start, end)
        daily_fiat_prices = await prices.map_fiat_daily_prices(
            ('btc', unpack_symbol(SYMBOL)[0]), start, end
        )
        benchmark_stats = get_benchmark_statistics(daily_fiat_prices['btc'])
        fees, filters = informant.get_fees_filters('binance', SYMBOL)

        logging.info('running backtest in rust solver, python solver, python trader ...')

        args = (
            daily_fiat_prices,
            benchmark_stats,
            strategies.MAMACX,
            start,
            end,
            Decimal('1.0'),
            candles,
            fees,
            filters,
            SYMBOL,
            INTERVAL,
            MISSED_CANDLE_POLICY,
            TRAILING_STOP,
            SHORT_PERIOD,
            LONG_PERIOD,
            NEG_THRESHOLD,
            POS_THRESHOLD,
            PERSISTENCE,
            SHORT_MA,
            LONG_MA,
        )
        rust_result = rust_solver.solve(*args)
        python_result = python_solver.solve(*args)

        trader = Trader(
            chandler,
            informant,
            'binance',
            SYMBOL,
            INTERVAL,
            start,
            end,
            Decimal('1.0'),
            lambda: strategies.MAMACX(
                SHORT_PERIOD,
                LONG_PERIOD,
                NEG_THRESHOLD,
                POS_THRESHOLD,
                PERSISTENCE,
                SHORT_MA,
                LONG_MA
            ),
            missed_candle_policy=MISSED_CANDLE_POLICY,
            trailing_stop=TRAILING_STOP,
            adjust_start=False
        )
        await trader.run()
        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, daily_fiat_prices, trader.summary
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
        logging.info(f'alpha {portfolio_stats.alpha}')
        logging.info(f'profit {trader.summary.profit}')
        logging.info(f'mean pos dur {trader.summary.mean_position_duration}')

        logging.info('done')


asyncio.run(main())
