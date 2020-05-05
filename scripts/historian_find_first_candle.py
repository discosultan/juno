import argparse
import asyncio
import logging

from juno import exchanges
from juno.components import Chandler, Historian, Trades
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.time import strftimestamp, strpinterval

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'
INTERVAL = '1h'

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default=SYMBOL)
parser.add_argument('interval', nargs='?', default=INTERVAL)
args = parser.parse_args()

interval = strpinterval(args.interval)


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[client])
    historian = Historian(chandler=chandler, storage=sqlite, exchanges=[client])
    async with client:
        candle = await historian.find_first_candle(exchange_name, args.symbol, interval)
        logging.info(strftimestamp(candle.time))


asyncio.run(main())
