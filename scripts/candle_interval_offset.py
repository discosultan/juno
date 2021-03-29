
import argparse
import asyncio
import logging

from juno import exchanges
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.time import strfinterval, strftimestamp, strpinterval
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('exchange', nargs='?', default='binance')
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument('interval', nargs='?', type=strpinterval, default='1d')
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
    storage = SQLite()
    trades = Trades(storage=storage, exchanges=[exchange])
    chandler = Chandler(storage=storage, exchanges=[exchange], trades=trades)

    async with exchange, storage, trades, chandler:
        candle = await chandler.get_first_candle(args.exchange, args.symbol, args.interval)

    offset = candle.time % args.interval
    logging.info(
        f'{args.exchange} {args.symbol} {strfinterval(args.interval)} candle '
        f'{strftimestamp(candle.time)} offset is {offset} ({strfinterval(offset)})'
    )


asyncio.run(main())
