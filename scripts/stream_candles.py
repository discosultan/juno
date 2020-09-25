import argparse
import asyncio
import logging
from itertools import product

import juno.json as json
from juno import exchanges, storages
from juno.asyncio import enumerate_async
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.math import floor_multiple
from juno.time import MIN_MS, strftimestamp, strpinterval, strptimestamp, time_ms
from juno.utils import get_module_type

INTERVAL = MIN_MS
CURRENT = floor_multiple(time_ms(), INTERVAL)
END = CURRENT + INTERVAL  # 1 future.
START = CURRENT - 2 * INTERVAL  # 2 historical.

CLOSED = True
FILL_MISSING_WITH_LAST = False
DUMP_AS_JSON = False
LOG_CANDLES = False

parser = argparse.ArgumentParser()
parser.add_argument('symbols', nargs='?', type=lambda s: s.split(','), default=['eth-btc'])
parser.add_argument(
    'intervals', nargs='?', type=lambda s: map(strpinterval, s.split(',')), default=[INTERVAL]
)
parser.add_argument('start', nargs='?', type=strptimestamp, default=START)
parser.add_argument('end', nargs='?', type=strptimestamp, default=END)
parser.add_argument('--exchange', '-e', default='binance')
parser.add_argument('--storage', default='sqlite')
args = parser.parse_args()


async def main() -> None:
    storage = get_module_type(storages, args.storage)()
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    trades = Trades(storage, [client])
    chandler = Chandler(trades=trades, storage=storage, exchanges=[client])
    async with client:
        logging.info(
            f'start {strftimestamp(args.start)} current {strftimestamp(CURRENT)} end '
            f'{strftimestamp(args.end)}'
        )
        await asyncio.gather(
            *(stream_candles(chandler, s, i) for s, i in product(args.symbols, args.intervals))
        )


async def stream_candles(chandler: Chandler, symbol: str, interval: int) -> None:
    candles = []
    async for i, candle in enumerate_async(chandler.stream_candles(
        args.exchange, symbol, interval, args.start, args.end, closed=CLOSED,
        fill_missing_with_last=FILL_MISSING_WITH_LAST
    )):
        assert not FILL_MISSING_WITH_LAST or candle.time == args.start + i * interval
        assert not CLOSED or candle.closed

        candles.append(candle)

        if LOG_CANDLES:
            historical_or_future = 'future' if candle.time >= CURRENT else 'historical'
            logging.info(f'{historical_or_future} candle {i}: {candle}')

    if DUMP_AS_JSON:
        with open(f'{args.exchange}_{symbol}_{interval}_candles.json', 'w') as f:
            json.dump(candles, f, indent=4)


asyncio.run(main())
