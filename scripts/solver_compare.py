import asyncio
import logging
from decimal import Decimal

from juno import components, exchanges, optimization, strategies, storages
from juno.asyncio import list_async
from juno.config import from_env, init_instance
from juno.time import HOUR_MS, strptimestamp


async def main() -> None:
    storage = storages.SQLite()
    exchange = init_instance(exchanges.Binance, from_env())
    informant = components.Informant(storage, [exchange])
    trades = components.Trades(storage, [exchange])
    chandler = components.Chandler(trades, storage, [exchange])
    rust_solver = optimization.Rust(chandler, informant)
    python_solver = optimization.Python()
    async with exchange, informant, rust_solver:
        candles = await list_async(chandler.stream_candles(
            'binance', 'eth-btc', HOUR_MS, strptimestamp('2017-07-01'), strptimestamp('2019-12-07')
        ))
        fees, filters = informant.get_fees_filters('binance', 'eth-btc')
        args = (
            strategies.MAMACX,
            Decimal('1.0'),
            candles,
            fees,
            filters,
            'eth-btc',
            HOUR_MS,
            2,
            Decimal('0.8486'),
            7,
            49,
            Decimal('-0.946'),
            Decimal('0.854'),
            6,
            'smma',
            'sma',
        )
        logging.info('solving rust')
        rust_result = rust_solver.solve(*args)
        logging.info(rust_result.mean_position_duration)

        logging.info('solving python')
        python_result = python_solver.solve(*args)
        logging.info(python_result.mean_position_duration)

        logging.info('done')


asyncio.run(main())
