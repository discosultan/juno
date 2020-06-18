import asyncio
import logging
from decimal import Decimal

from juno import strategies, time
from juno.components import Chandler, Informant, Prices, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.math import floor_multiple
from juno.optimizer import Optimizer
from juno.solvers import Rust
from juno.statistics import analyse_benchmark, analyse_portfolio
from juno.storages import SQLite
from juno.traders import Basic
from juno.typing import TypeConstructor
from juno.utils import construct, extract_public, get_module_type, unpack_symbol

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
    informant = Informant(storage=sqlite, exchanges=exchanges)
    prices = Prices(chandler=chandler)
    trader = Basic(chandler=chandler, informant=informant, exchanges=exchanges)
    rust_solver = Rust(informant=informant)
    optimizer = Optimizer(
        solver=rust_solver,
        chandler=chandler,
        informant=informant,
        prices=prices,
        trader=trader,
    )
    async with binance, coinbase, informant, rust_solver:
        first_candle = await chandler.get_first_candle(exchange_name, SYMBOL, INTERVAL)
        training_start = floor_multiple(first_candle.time, INTERVAL)
        validation_end = floor_multiple(time.time_ms(), INTERVAL)
        validation_start = floor_multiple(
            training_start + int((validation_end - training_start) * TRAINING_VALIDATION_SPLIT),
            INTERVAL
        )

        optimization_summary = await optimizer.run(Optimizer.Config(
            exchange=exchange_name,
            start=training_start,
            end=validation_start,
            quote=QUOTE,
            strategy=TypeConstructor.from_type(get_module_type(strategies, STRATEGY_TYPE)),
            symbols=[SYMBOL],
            intervals=[INTERVAL],
            population_size=50,
            max_generations=100,
            mutation_probability=Decimal('0.2'),
            verbose=True,
        ))

        logging.info(
            f'training trading summary: {extract_public(optimization_summary.trading_summary)}'
        )
        logging.info(f'training portfolio stats: {optimization_summary.portfolio_stats}')

        trading_summary = await trader.run(construct(
            Basic.Config,
            optimization_summary.trading_config,
            start=validation_start,
            end=validation_end,
        ))

        base_asset, quote_asset = unpack_symbol(SYMBOL)
        fiat_prices = await prices.map_prices(
            exchange=optimization_summary.trading_config.exchange,
            symbols=[SYMBOL],
            start=validation_start,
            end=validation_end,
        )
        benchmark = analyse_benchmark(fiat_prices[quote_asset])
        portfolio = analyse_portfolio(benchmark.g_returns, fiat_prices, trading_summary)

        logging.info(f'trading summary: {extract_public(trading_summary)}')
        logging.info(f'benchmark stats: {benchmark.stats}')
        logging.info(f'portfolio stats: {portfolio.stats}')


asyncio.run(main())
