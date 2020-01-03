import asyncio
import logging
from decimal import Decimal

from juno import components, exchanges, optimization, strategies, storages, time
from juno.asyncio import list_async
from juno.config import config_from_env, init_instance
from juno.math import floor_multiple
from juno.strategies import MA
from juno.time import strptimestamp
from juno.trading import MissedCandlePolicy, Trader

# SYMBOL = 'eth-btc'
# INTERVAL = time.HOUR_MS
# START = '2017-07-01'
# END = '2019-12-07'
# MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
# TRAILING_STOP = Decimal('0.8486')

# SHORT_PERIOD = 7
# LONG_PERIOD = 49
# NEG_THRESHOLD = Decimal('-0.946')
# POS_THRESHOLD = Decimal('0.854')
# PERSISTENCE = 6
# SHORT_MA = MA.SMMA
# LONG_MA = MA.SMA

SYMBOL = 'enj-bnb'
INTERVAL = time.DAY_MS
START = '2019-01-01'
END = '2019-12-22'
MISSED_CANDLE_POLICY = MissedCandlePolicy.LAST
TRAILING_STOP = Decimal('0.0')

SHORT_PERIOD = 1
LONG_PERIOD = 8
NEG_THRESHOLD = Decimal('-0.624')
POS_THRESHOLD = Decimal('0.893')
PERSISTENCE = 2
SHORT_MA = MA.SMMA
LONG_MA = MA.SMMA


async def main() -> None:
    start = floor_multiple(strptimestamp(START), INTERVAL)
    end = floor_multiple(strptimestamp(END), INTERVAL)

    storage = storages.SQLite()
    exchange = init_instance(exchanges.Binance, config_from_env())
    informant = components.Informant(storage, [exchange])
    trades = components.Trades(storage, [exchange])
    chandler = components.Chandler(trades, storage, [exchange])
    rust_solver = optimization.Rust(chandler, informant)
    python_solver = optimization.Python()
    async with exchange, informant, rust_solver:
        candles = await list_async(chandler.stream_candles(
            'binance', SYMBOL, INTERVAL, start, end
        ))
        fees, filters = informant.get_fees_filters('binance', SYMBOL)

        logging.info('running backtest in rust solver, python solver, python trader ...')

        args = (
            strategies.MAMACX,
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

        logging.info('rust solver')
        logging.info(rust_result.profit)
        logging.info(rust_result.mean_position_duration)

        logging.info('python solver')
        logging.info(python_result.profit)
        logging.info(python_result.mean_position_duration)

        logging.info('python trader')
        logging.info(trader.summary.profit)
        logging.info(trader.summary.mean_position_duration)

        logging.info('done')


asyncio.run(main())
