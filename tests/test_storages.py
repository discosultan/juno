import asyncio
from decimal import Decimal

import pytest

from juno import Candle, Fees
from juno.filters import Filters
from juno.storages import Memory
from juno.utils import list_async

from .utils import new_candle

DECIMAL_TOO_PRECISE_FOR_FLOAT = Decimal('0.1234567890123456789012345678901234567890123456789')


@pytest.fixture
async def memory(request):
    async with Memory() as storage:
        yield storage


async def test_memory_store_candles(loop, memory):
    candles = [new_candle(time=0, close=DECIMAL_TOO_PRECISE_FOR_FLOAT), new_candle(time=1)]
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
    candle = {'foo': new_candle(time=1, close=DECIMAL_TOO_PRECISE_FOR_FLOAT)}

    await memory.set_map(key='key', type_=Candle, items=candle)
    out_candle, _ = await memory.get_map(key='key', type_=Candle)

    assert out_candle == candle


async def test_memory_get_map_missing(loop, memory):
    item, _ = await memory.get_map(key='key', type_=Candle)

    assert item is None


async def test_memory_set_map_twice_get_map(loop, memory):
    candle1 = {'foo': new_candle(time=1)}
    candle2 = {'foo': new_candle(time=2)}

    await memory.set_map(key='key', type_=Candle, items=candle1)
    await memory.set_map(key='key', type_=Candle, items=candle2)
    out_candle, _ = await memory.get_map(key='key', type_=Candle)

    assert out_candle == candle2


async def test_memory_set_different_maps(loop, memory):
    fees = {'foo': Fees.none()}
    filters = {'foo': Filters.none()}

    await asyncio.gather(
        memory.set_map(key='key', type_=Fees, items=fees),
        memory.set_map(key='key', type_=Filters, items=filters))
    (out_fees, _), (out_filters, _) = await asyncio.gather(
        memory.get_map(key='key', type_=Fees),
        memory.get_map(key='key', type_=Filters))

    assert out_fees == fees
    assert out_filters == filters
