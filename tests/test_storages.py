import asyncio
from decimal import Decimal

import pytest

from juno import Candle, Fees, Filters, SymbolsInfo, Trade
from juno.asyncio import list_async
from juno.storages import Memory

from .utils import types_match

DECIMAL_TOO_PRECISE_FOR_FLOAT = Decimal('0.1234567890123456789012345678901234567890123456789')


@pytest.fixture
async def memory(loop):
    return Memory()
    # async with Memory() as storage:
    #     yield storage


@pytest.mark.parametrize(
    'items', [
        [
            Candle(time=0, close=DECIMAL_TOO_PRECISE_FOR_FLOAT),
            Candle(time=1),
            Candle(time=3),
        ],
        [
            Trade(time=0, price=Decimal('1.0'), size=Decimal('2.0')),
            Trade(time=3, price=Decimal('4.0'), size=Decimal('5.0')),
            Trade(time=6, price=Decimal('7.0'), size=Decimal('8.0')),
        ],
    ]
)
async def test_memory_store_objects_and_span(memory, items):
    type_ = type(items[0])
    start = items[0].time
    end = items[-1].time + 1

    await memory.store_time_series_and_span(
        key='key', type=type_, items=items, start=start, end=end
    )
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('key', type_, start, end)),
        list_async(memory.stream_time_series('key', type_, start, end))
    )

    assert output_spans == [(start, end)]
    assert output_items == items


async def test_memory_stream_missing_series(memory):
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('key', Candle, 0, 10)),
        list_async(memory.stream_time_series('key', Candle, 0, 10))
    )

    assert output_spans == []
    assert output_items == []


async def test_memory_store_and_stream_empty_series(memory):
    await memory.store_time_series_and_span(key='key', type=Candle, items=[], start=0, end=5)
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('key', Candle, 0, 5)),
        list_async(memory.stream_time_series('key', Candle, 0, 5))
    )

    assert output_spans == [(0, 5)]
    assert output_items == []


@pytest.mark.parametrize('item', [
    Candle(time=1, close=Decimal('1.0')),
    SymbolsInfo(),
])
async def test_memory_set_get(memory, item):
    item_type = type(item)

    await memory.set(key='key', type_=item_type, item=item)
    out_item, _ = await memory.get(key='key', type_=item_type)

    assert out_item == item
    assert types_match(out_item)


async def test_memory_set_get_map(memory):
    candle = {'foo': Candle(time=1, close=Decimal('1.0'))}

    await memory.set_map(key='key', type_=Candle, items=candle)
    out_candle, _ = await memory.get_map(key='key', type_=Candle)

    assert out_candle == candle


async def test_memory_get_map_missing(memory):
    item, _ = await memory.get_map(key='key', type_=Candle)

    assert item is None


async def test_memory_set_map_twice_get_map(memory):
    candle1 = {'foo': Candle(time=1)}
    candle2 = {'foo': Candle(time=2)}

    await memory.set_map(key='key', type_=Candle, items=candle1)
    await memory.set_map(key='key', type_=Candle, items=candle2)
    out_candle, _ = await memory.get_map(key='key', type_=Candle)

    assert out_candle == candle2


async def test_memory_set_get_different_maps(memory):
    fees = {'foo': Fees()}
    filters = {'foo': Filters()}

    await asyncio.gather(
        memory.set_map(key='key', type_=Fees, items=fees),
        memory.set_map(key='key', type_=Filters, items=filters)
    )
    (out_fees, _), (out_filters, _) = await asyncio.gather(
        memory.get_map(key='key', type_=Fees),
        memory.get_map(key='key', type_=Filters),
    )

    assert out_fees == fees
    assert out_filters == filters
