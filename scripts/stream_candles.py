import argparse
import asyncio
import logging
from itertools import product

import juno.json as json
from juno import exchanges, storages
from juno.asyncio import enumerate_async
from juno.components import Chandler
from juno.config import from_env, init_instance
from juno.math import floor_multiple_offset
from juno.time import MIN_MS, strftimestamp, strpinterval, strptimestamp, time_ms
from juno.trades import Trades
from juno.utils import get_module_type

CLOSED = True
FILL_MISSING_WITH_LAST = False
DUMP_AS_JSON = False
LOG_CANDLES = False

parser = argparse.ArgumentParser()
parser.add_argument('symbols', nargs='?', type=lambda s: s.split(','), default=['eth-btc'])
parser.add_argument(
    'intervals', nargs='?', type=lambda s: map(strpinterval, s.split(',')), default=[MIN_MS]
)
parser.add_argument('start', nargs='?', type=strptimestamp, default=None)
parser.add_argument('end', nargs='?', type=strptimestamp, default=None)
parser.add_argument('--exchange', '-e', default='binance')
parser.add_argument('--storage', default='sqlite')
args = parser.parse_args()

now = time_ms()


async def main() -> None:
    storage = get_module_type(storages, args.storage)()
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    trades = Trades(storage=storage, exchange_sessions=[client])
    chandler = Chandler(trades=trades, storage=storage, exchanges=[client])
    async with client, trades, chandler:
        await asyncio.gather(
            *(stream_candles(chandler, s, i)
              for s, i in product(args.symbols, args.intervals))
        )


async def stream_candles(chandler: Chandler, symbol: str, interval: int) -> None:
    interval_offset = chandler.get_interval_offset(args.exchange, interval)

    start = (
        (await chandler.get_first_candle(args.exchange, symbol, interval)).time
        if args.start is None else floor_multiple_offset(args.start, interval, interval_offset)
    )
    current = floor_multiple_offset(now, interval, interval_offset)
    end = (
        current if args.end is None
        else floor_multiple_offset(args.end, interval, interval_offset)
    )

    logging.info(
        f'start {strftimestamp(start)} current {strftimestamp(current)} end '
        f'{strftimestamp(end)}'
    )

    candles = []
    async for i, candle in enumerate_async(chandler.stream_candles(
        args.exchange, symbol, interval, start, end, closed=CLOSED,
        fill_missing_with_last=FILL_MISSING_WITH_LAST
    )):
        assert not FILL_MISSING_WITH_LAST or candle.time == start + i * interval
        assert not CLOSED or candle.closed

        if DUMP_AS_JSON:
            candles.append(candle)

        if LOG_CANDLES:
            historical_or_future = 'future' if candle.time >= current else 'historical'
            logging.info(f'{historical_or_future} candle {i}: {candle}')

    if DUMP_AS_JSON:
        with open(f'{args.exchange}_{symbol}_{interval}_candles.json', 'w') as f:
            json.dump(candles, f, indent=4)


asyncio.run(main())
