import asyncio
from decimal import Decimal
from typing import Dict, List

import pytest

from juno import Candle, ExchangeInfo, Fees, Filters, Ticker, Trade, storages
from juno.asyncio import list_async
from juno.typing import types_match

DECIMAL_TOO_PRECISE_FOR_FLOAT = Decimal('0.1234567890123456789012345678901234567890123456789')


@pytest.fixture
async def memory(loop):
    async with storages.Memory() as storage:
        yield storage


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
async def test_memory_store_objects_and_span(memory: storages.Memory, items) -> None:
    type_ = type(items[0])
    start = items[0].time
    end = items[-1].time + 1

    await memory.store_time_series_and_span(
        shard='shard', name='item', items=items, start=start, end=end
    )
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'name', start, end)),
        list_async(memory.stream_time_series('shard', 'name', type_, start, end))
    )

    assert output_spans == [(start, end)]
    assert output_items == items


async def test_memory_stream_missing_series(memory: storages.Memory) -> None:
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'name', 0, 10)),
        list_async(memory.stream_time_series('shard', 'name', Candle, 0, 10))
    )

    assert output_spans == []
    assert output_items == []


async def test_memory_store_and_stream_empty_series(memory: storages.Memory) -> None:
    await memory.store_time_series_and_span('shard', 'name', items=[], start=0, end=5)
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'name', 0, 5)),
        list_async(memory.stream_time_series('shard', 'name', Candle, 0, 5))
    )

    assert output_spans == [(0, 5)]
    assert output_items == []


@pytest.mark.parametrize('item,type_', [
    (Candle(time=1, close=Decimal('1.0')), Candle),
    (ExchangeInfo(candle_intervals=[1, 2]), ExchangeInfo),
    ([Ticker(symbol='eth-btc', volume=Decimal('1.0'), quote_volume=Decimal('0.1'))], List[Ticker]),
    ({'foo': Fees(maker=Decimal('0.01'), taker=Decimal('0.02'))}, Dict[str, Fees]),
])
async def test_memory_set_get(memory: storages.Memory, item, type_) -> None:
    await memory.set('shard', 'name', item)
    out_item = await memory.get('shard', 'name', type_)

    assert out_item == item
    assert types_match(out_item, type_)


async def test_memory_get_missing(memory: storages.Memory) -> None:
    item = await memory.get('shard', 'name', Candle)

    assert item is None


async def test_memory_set_twice_get(memory: storages.Memory) -> None:
    candle1 = Candle(time=1)
    candle2 = Candle(time=2)

    await memory.set('shard', 'name', candle1)
    await memory.set('shard', 'name', candle2)
    out_candle = await memory.get('shard', 'name', Candle)

    assert out_candle == candle2


async def test_memory_set_get_different(memory: storages.Memory) -> None:
    fees = {'foo': Fees()}
    filters = {'foo': Filters()}

    await asyncio.gather(
        memory.set('shard', 'name', fees),
        memory.set('shard', 'name', filters)
    )
    out_fees, out_filters = await asyncio.gather(
        memory.get('shard', 'name', Dict[str, Fees]),
        memory.get('shard', 'name', Dict[str, Filters]),
    )

    assert out_fees == fees
    assert out_filters == filters
