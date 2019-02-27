import asyncio
from decimal import Decimal

import pytest

from juno import Candle
from juno.storages import Memory
from juno.utils import list_async

DECIMAL_TOO_PRECISE_FOR_FLOAT = Decimal('0.1234567890123456789012345678901234567890123456789')


@pytest.fixture
async def memory(request):
    async with Memory() as storage:
        yield storage


async def test_memory_store_candles(loop, memory):
    candles = [_new_candle(time=0, close=DECIMAL_TOO_PRECISE_FOR_FLOAT), _new_candle(time=1)]
    start, end = 0, 2

    await memory.store_candles_and_span(
        key='key',
        candles=candles,
        start=start,
        end=end)
    spans, candles = await asyncio.gather(
        list_async(memory.stream_candle_spans('key', 0, 2)),
        list_async(memory.stream_candles('key', 0, 2)))

    assert spans == [(start, end)]
    assert candles == candles


async def test_memory_store_get_map(loop, memory):
    candle = {'foo': _new_candle(time=1, close=DECIMAL_TOO_PRECISE_FOR_FLOAT)}

    await memory.set_map(key='key', items=candle)
    stored_candle, _ = await memory.get_map(key='key', item_cls=Candle)

    assert stored_candle == candle


async def test_memory_get_map_missing(loop, memory):
    item, _ = await memory.get_map(key='key', item_cls=Candle)

    assert item is None


async def test_memory_set_map_twice_get_map(loop, memory):
    candle1 = {'foo': _new_candle(time=1)}
    candle2 = {'foo': _new_candle(time=2)}

    await memory.set_map(key='key', items=candle1)
    await memory.set_map(key='key', items=candle2)
    stored_candle, _ = await memory.get_map(key='key', item_cls=Candle)

    assert stored_candle == candle2


def _new_candle(time=0, close=Decimal(0)):
    return Candle(
        time=time,
        open=Decimal(0),
        high=Decimal(0),
        low=Decimal(0),
        close=close,
        volume=Decimal(0))
