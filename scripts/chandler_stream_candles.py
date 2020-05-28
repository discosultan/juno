import argparse
import asyncio
import logging

import juno.json as json
from juno import exchanges, storages
from juno.asyncio import enumerate_async
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.modules import get_module_type
from juno.time import MIN_MS, strftimestamp, strpinterval, strptimestamp, time_ms

INTERVAL = MIN_MS
CURRENT = floor_multiple(time_ms(), INTERVAL)
END = CURRENT + INTERVAL  # 1 future.
START = CURRENT - 2 * INTERVAL  # 2 historical.

CLOSED = True
DUMP_AS_JSON = False

parser = argparse.ArgumentParser()
parser.add_argument('exchange', nargs='?', default='binance')
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument('interval', nargs='?', type=strpinterval, default=INTERVAL)
parser.add_argument('start', nargs='?', type=strptimestamp, default=START)
parser.add_argument('end', nargs='?', type=strptimestamp, default=END)
parser.add_argument('--storage', default='sqlite')
args = parser.parse_args()


async def main() -> None:
    storage = get_module_type(storages, args.storage)()
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    trades = Trades(storage, [client])
    chandler = Chandler(trades=trades, storage=storage, exchanges=[client])
    candles = []
    async with client:
        logging.info(
            f'start {strftimestamp(args.start)} current {strftimestamp(CURRENT)} end '
            f'{strftimestamp(args.end)}'
        )
        async for i, candle in enumerate_async(chandler.stream_candles(
            args.exchange, args.symbol, args.interval, args.start, args.end, closed=CLOSED,
            fill_missing_with_last=True
        )):
            assert candle.time == args.start + i * args.interval
            assert not CLOSED or candle.closed
            historical_or_future = 'future' if candle.time >= CURRENT else 'historical'
            logging.info(f'{historical_or_future} candle {i}: {candle}')
            candles.append(candle)

    if DUMP_AS_JSON:
        with open(f'{args.exchange}_{args.symbol}_{args.interval}_candles.json', 'w') as f:
            json.dump(candles, f, indent=4)


asyncio.run(main())
