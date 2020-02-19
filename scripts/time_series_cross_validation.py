import asyncio
import logging
from decimal import Decimal

from juno import strategies, time
from juno.components import Chandler, Historian, Informant, Prices, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.math import floor_multiple
from juno.optimization import Optimizer, Rust
from juno.storages import SQLite
from juno.trading import Trader, analyse_benchmark, analyse_portfolio
from juno.utils import asdict, unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = time.HOUR_MS
TRAINING_VALIDATION_SPLIT = 0.75
QUOTE = Decimal('1.0')
STRATEGY_TYPE = strategies.MAMACX


async def main() -> None:
    sqlite = SQLite()
    binance = init_instance(Binance, from_env())
    coinbase = init_instance(Coinbase, from_env())
    exchanges = [binance, coinbase]
    exchange_name = Binance.__name__.lower()
    trades = Trades(sqlite, exchanges)
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=exchanges)
    historian = Historian(chandler=chandler, storage=sqlite, exchanges=exchanges)
    informant = Informant(sqlite, exchanges)
    prices = Prices(chandler)
    trader = Trader(chandler, informant)
    rust_solver = Rust()
    optimizer = Optimizer(rust_solver, chandler, informant, prices, trader)
    async with binance, coinbase, informant, rust_solver:
        first_candle = await historian.find_first_candle(exchange_name, SYMBOL, INTERVAL)
        training_start = floor_multiple(first_candle.time, INTERVAL)
        validation_end = floor_multiple(time.time_ms(), INTERVAL)
        validation_start = floor_multiple(
            training_start + int((validation_end - training_start) * TRAINING_VALIDATION_SPLIT),
            INTERVAL
        )

        optimization_summary = await optimizer.run(
            exchange=exchange_name,
            start=training_start,
            end=validation_start,
            quote=QUOTE,
            strategy_type=STRATEGY_TYPE,
            symbols=[SYMBOL],
            intervals=[INTERVAL],
            population_size=50,
            max_generations=100,
            mutation_probability=Decimal('0.2'),
            verbose=True,
        )

        logging.info(
            'training trading summary: '
            f'{asdict(optimization_summary.trading_summary)}'
        )
        logging.info(
            'training portfolio stats: '
            f'{asdict(optimization_summary.portfolio_stats)}'
        )

        tc = optimization_summary.trading_config

        trading_summary = await trader.run(
            start=validation_start,
            end=validation_end,
            exchange=tc.exchange,
            symbol=tc.symbol,
            interval=tc.interval,
            quote=tc.quote,
            missed_candle_policy=tc.missed_candle_policy,
            trailing_stop=tc.trailing_stop,
            strategy_type=tc.strategy_type,
            strategy_kwargs=tc.strategy_kwargs,
        )

        base_asset, quote_asset = unpack_symbol(SYMBOL)
        fiat_daily_prices = await prices.map_fiat_daily_prices(
            (base_asset, quote_asset), validation_start, validation_end
        )
        benchmark = analyse_benchmark(fiat_daily_prices[quote_asset])
        portfolio = analyse_portfolio(benchmark.g_returns, fiat_daily_prices, trading_summary)

        logging.info(f'trading summary: {asdict(trading_summary)}')
        logging.info(f'benchmark stats: {asdict(benchmark.stats)}')
        logging.info(f'portfolio stats: {asdict(portfolio.stats)}')

    logging.info('done')


asyncio.run(main())
