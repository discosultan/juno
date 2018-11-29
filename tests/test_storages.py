import asyncio

from juno import Candle, Span
from juno.storages import Memory
from juno.utils import list_async


def _new_candle(time=0):
    return Candle(
        time=time,
        open=0.0,
        high=0.0,
        low=0.0,
        close=0.0,
        volume=0.0)


async def test_memory_store_candles(loop):
    async with Memory() as storage:
        candles = [_new_candle(time=0), _new_candle(time=1)]
        span = Span(start=0, end=2)

        await storage.store_candles_and_span(
            exchange='exchange',
            symbol='eth-btc',
            interval=1,
            candles=candles,
            span=span)
        spans, candles = await asyncio.gather(
            list_async(storage.stream_candle_spans('exchange', 'eth-btc', 0, 2)),
            list_async(storage.stream_candles('exchange', 'eth-btc', 0, 2)))

        assert spans == [span]
        assert candles == candles
