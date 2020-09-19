import argparse
import asyncio
import logging

from juno import exchanges
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.time import HOUR_MS, strfinterval, strftimestamp, strpinterval, time_ms

EXCHANGE_TYPE = exchanges.Binance

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument('interval', nargs='?', type=strpinterval, default=HOUR_MS)
args = parser.parse_args()


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    trades = Trades(sqlite, [client])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[client])
    async with client:
        first_candle, last_candle = await asyncio.gather(
            chandler.get_first_candle(exchange_name, args.symbol, args.interval),
            chandler.get_last_candle(exchange_name, args.symbol, args.interval),
        )
        logging.info(
            f'got the following {args.symbol} {strfinterval(args.interval)} candles at '
            f'{strftimestamp(time_ms())}:'
        )
        logging.info(f'    first - {strftimestamp(first_candle.time)}')
        logging.info(f'    last  - {strftimestamp(last_candle.time)}')


asyncio.run(main())
