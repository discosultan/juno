import asyncio
import logging
from decimal import Decimal

from juno import components, exchanges, optimization, storages, strategies, time
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.strategies import MA
from juno.trading import (
    MissedCandlePolicy, Trader, TradingResult, get_benchmark_statistics, get_portfolio_statistics
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

# SYMBOL = 'enj-bnb'  # NB: ONLY BTC QUOTE SUPPORTED IN STATISTICS
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

# SYMBOL = 'eth-btc'
# INTERVAL = time.DAY_MS
# START = time.strptimestamp('2019-01-01')
# END = time.strptimestamp('2019-02-01')
# MISSED_CANDLE_POLICY = MissedCandlePolicy.IGNORE
# TRAILING_STOP = Decimal('0.0')

# SHORT_PERIOD = 17
# LONG_PERIOD = 24
# NEG_THRESHOLD = Decimal('-0.667')
# POS_THRESHOLD = Decimal('0.926')
# PERSISTENCE = 0
# SHORT_MA = MA.SMMA
# LONG_MA = MA.SMA

# SYMBOL = 'eth-btc'
# INTERVAL = 1800000
# START = 1499990400000
# END = 1561939200000
# MISSED_CANDLE_POLICY = MissedCandlePolicy.IGNORE
# TRAILING_STOP = Decimal('0.0')

# SHORT_PERIOD = 93
# LONG_PERIOD = 94
# NEG_THRESHOLD = Decimal('-0.646')
# POS_THRESHOLD = Decimal('0.53')
# PERSISTENCE = 4
# SHORT_MA = MA.EMA2
# LONG_MA = MA.EMA2


async def main() -> None:
    start = floor_multiple(START, INTERVAL)
    end = floor_multiple(END, INTERVAL)
    quote = Decimal('1.0')

    storage = storages.SQLite()
    binance = init_instance(exchanges.Binance, from_env())
    coinbase = init_instance(exchanges.Coinbase, from_env())
    exchange_list = [binance, coinbase]
    informant = components.Informant(storage, exchange_list)
    trades = components.Trades(storage, exchange_list)
    chandler = components.Chandler(trades=trades, storage=storage, exchanges=exchange_list)
    prices = components.Prices(chandler)
    rust_solver = optimization.Rust(informant)
    python_solver = optimization.Python(informant)
    trader = Trader(chandler, informant)
    async with binance, coinbase, informant, rust_solver:
        candles = await chandler.list_candles('binance', SYMBOL, INTERVAL, start, end)
        base_asset, quote_asset = unpack_symbol(SYMBOL)
        fiat_daily_prices = await prices.map_fiat_daily_prices(
            (base_asset, quote_asset), start, end
        )
        benchmark_stats = get_benchmark_statistics(fiat_daily_prices[quote_asset])

        logging.info('running backtest in rust solver, python solver, python trader ...')

        args = (
            fiat_daily_prices,
            benchmark_stats,
            strategies.MAMACX,
            start,
            end,
            quote,
            candles,
            'binance',
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

        trader_result = TradingResult(quote=quote)
        await trader.run(
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=quote,
            new_strategy=lambda: strategies.MAMACX(
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
            adjust_start=False,
            result=trader_result
        )
        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, fiat_daily_prices, trader_result
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
        logging.info(f'profit {trader_result.profit}')
        logging.info(f'mean pos dur {trader_result.mean_position_duration}')

        logging.info('done')


asyncio.run(main())
