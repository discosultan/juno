import asyncio
import logging

from juno import exchanges
from juno.components import Chandler, Historian, Trades
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.time import HOUR_MS, strftimestamp

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'
INTERVAL = HOUR_MS


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[client])
    historian = Historian(chandler=chandler, storage=sqlite)
    async with client:
        time = await historian.find_first_candle_time(exchange_name, SYMBOL, INTERVAL)
        logging.info(strftimestamp(time))
        logging.info('done')


asyncio.run(main())
