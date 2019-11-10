import asyncio
from decimal import Decimal

import pytest

from juno import Candle, Fees, Filters, SymbolsInfo, Trade
from juno.asyncio import list_async
from juno.storages import Memory, SQLite

from .utils import new_candle, types_match

DECIMAL_TOO_PRECISE_FOR_FLOAT = Decimal('0.1234567890123456789012345678901234567890123456789')


@pytest.fixture
async def memory(request):
    return SQLite()
    # async with Memory() as storage:
    #     yield storage


@pytest.mark.parametrize('items', [
    [
        new_candle(time=0, close=DECIMAL_TOO_PRECISE_FOR_FLOAT),
        new_candle(time=1),
        new_candle(time=3),
    ],
    [
        Trade(time=0, price=Decimal(1), size=Decimal(2)),
        Trade(time=3, price=Decimal(4), size=Decimal(5)),
        Trade(time=6, price=Decimal(7), size=Decimal(8)),
    ],
])
async def test_memory_store_objects_and_span(loop, memory, items):
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


@pytest.mark.parametrize('item', [
    new_candle(time=1, close=Decimal(1)),
    SymbolsInfo.none(),
])
async def test_memory_set_get(loop, memory, item):
    item_type = type(item)

    await memory.set(key='key', type_=item_type, item=item)
    out_item, _ = await memory.get(key='key', type_=item_type)

    assert out_item == item
    assert types_match(out_item)


async def test_memory_set_get_map(loop, memory):
    candle = {'foo': new_candle(time=1, close=Decimal(1))}

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
        memory.set_map(key='key', type_=Filters, items=filters)
    )
    (out_fees, _), (out_filters, _) = await asyncio.gather(
        memory.get_map(key='key', type_=Fees),
        memory.get_map(key='key', type_=Filters),
    )

    assert out_fees == fees
    assert out_filters == filters
