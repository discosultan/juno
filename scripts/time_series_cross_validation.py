import asyncio
import logging
from decimal import Decimal

from juno import time
from juno.components import Chandler, Historian, Informant, Prices, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.math import floor_multiple
from juno.optimization import Optimizer, Rust
from juno.storages import SQLite
from juno.trading import Trader, analyse_benchmark, analyse_portfolio
from juno.utils import tonamedtuple, unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = time.HOUR_MS
TRAINING_VALIDATION_SPLIT = 0.75
QUOTE = Decimal('1.0')
STRATEGY_TYPE = 'mamacx'


async def main() -> None:
    sqlite = SQLite()
    binance = init_instance(Binance, from_env())
    coinbase = init_instance(Coinbase, from_env())
    exchanges = [binance, coinbase]
    exchange_name = Binance.__name__.lower()
    trades = Trades(sqlite, exchanges)
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=exchanges)
    historian = Historian(chandler=chandler, storage=sqlite, exchanges=exchanges)
    informant = Informant(storage=sqlite, exchanges=exchanges)
    prices = Prices(chandler=chandler, historian=historian)
    trader = Trader(chandler=chandler, informant=informant, exchanges=exchanges)
    rust_solver = Rust(informant=informant)
    optimizer = Optimizer(
        solver=rust_solver,
        chandler=chandler,
        informant=informant,
        prices=prices,
        trader=trader,
        historian=historian,
    )
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
            strategy=STRATEGY_TYPE,
            symbols=[SYMBOL],
            intervals=[INTERVAL],
            population_size=50,
            max_generations=100,
            mutation_probability=Decimal('0.2'),
            verbose=True,
        )
        best = optimization_summary.best[0]

        logging.info(
            f'training trading summary: {tonamedtuple(best.trading_summary)}'
        )
        logging.info(f'training portfolio stats: {best.portfolio_stats}')

        tc = best.trading_config

        trading_summary = await trader.run(Trader.Config(
            start=validation_start,
            end=validation_end,
            exchange=tc.exchange,
            symbol=tc.symbol,
            interval=tc.interval,
            quote=tc.quote,
            missed_candle_policy=tc.missed_candle_policy,
            trailing_stop=tc.trailing_stop,
            strategy=tc.strategy,
            strategy_kwargs=tc.strategy_kwargs,
        ))

        base_asset, quote_asset = unpack_symbol(SYMBOL)
        fiat_daily_prices = await prices.map_prices(
            exchange=tc.exchange,
            symbols=[SYMBOL],
            start=validation_start,
            end=validation_end,
        )
        benchmark = analyse_benchmark(fiat_daily_prices[quote_asset])
        portfolio = analyse_portfolio(benchmark.g_returns, fiat_daily_prices, trading_summary)

        logging.info(f'trading summary: {tonamedtuple(trading_summary)}')
        logging.info(f'benchmark stats: {benchmark.stats}')
        logging.info(f'portfolio stats: {portfolio.stats}')


asyncio.run(main())
