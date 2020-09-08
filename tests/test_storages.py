import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, NamedTuple, Optional, Union

import pytest

from juno import Candle, ExchangeInfo, Fees, Fill, Filters, Ticker, Trade, storages
from juno.asyncio import list_async
from juno.trading import CloseReason, Position, TradingSummary
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
        shard='shard', key='key', items=items, start=start, end=end
    )
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'key', start, end)),
        list_async(memory.stream_time_series('shard', 'key', type_, start, end))
    )

    assert output_spans == [(start, end)]
    assert output_items == items


async def test_memory_stream_missing_series(memory: storages.Memory) -> None:
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'key', 0, 10)),
        list_async(memory.stream_time_series('shard', 'key', Candle, 0, 10))
    )

    assert output_spans == []
    assert output_items == []


async def test_memory_store_and_stream_empty_series(memory: storages.Memory) -> None:
    await memory.store_time_series_and_span('shard', 'key', items=[], start=0, end=5)
    output_spans, output_items = await asyncio.gather(
        list_async(memory.stream_time_series_spans('shard', 'key', 0, 5)),
        list_async(memory.stream_time_series('shard', 'key', Candle, 0, 5))
    )

    assert output_spans == [(0, 5)]
    assert output_items == []


async def test_stream_time_series_spans_merges_adjacent(memory: storages.Memory) -> None:
    await asyncio.gather(
        memory.store_time_series_and_span('shard', 'key', items=[], start=1, end=3),
        memory.store_time_series_and_span('shard', 'key', items=[], start=3, end=4),
    )

    output_spans = await list_async(memory.stream_time_series_spans('shard', 'key'))

    assert output_spans == [(1, 4)]


@pytest.mark.parametrize('item,type_', [
    (Candle(time=1, close=Decimal('1.0')), Candle),
    (ExchangeInfo(candle_intervals=[1, 2]), ExchangeInfo),
    (
        {
            'eth-btc': Ticker(
                volume=Decimal('1.0'),
                quote_volume=Decimal('0.1'),
                price=Decimal('1.0'),
            ),
        },
        Dict[str, Ticker],
    ),
    ({'foo': Fees(maker=Decimal('0.01'), taker=Decimal('0.02'))}, Dict[str, Fees]),
    (
        Position.Long(
            exchange='exchange',
            symbol='eth-btc',
            open_time=1,
            open_fills=[Fill()],
            close_time=2,
            close_fills=[Fill()],
            close_reason=CloseReason.STRATEGY,
        ),
        Position.Long,
    ),
    (TradingSummary(start=1, quote=Decimal('1.0'), quote_asset='btc'), TradingSummary),
])
async def test_memory_set_get(memory: storages.Memory, item, type_) -> None:
    await memory.set('shard', 'key', item)
    out_item = await memory.get('shard', 'key', type_)

    assert out_item == item
    assert types_match(out_item, type_)


async def test_memory_get_missing(memory: storages.Memory) -> None:
    item = await memory.get('shard', 'key', Candle)

    assert item is None


async def test_memory_set_twice_get(memory: storages.Memory) -> None:
    candle1 = Candle(time=1)
    candle2 = Candle(time=2)

    await memory.set('shard', 'key', candle1)
    await memory.set('shard', 'key', candle2)
    out_candle = await memory.get('shard', 'key', Candle)

    assert out_candle == candle2


async def test_memory_set_get_different(memory: storages.Memory) -> None:
    fees = {'foo': Fees()}
    filters = {'foo': Filters()}

    await asyncio.gather(
        memory.set('shard', 'fees', fees),
        memory.set('shard', 'filters', filters)
    )
    out_fees, out_filters = await asyncio.gather(
        memory.get('shard', 'fees', Dict[str, Fees]),
        memory.get('shard', 'filters', Dict[str, Filters]),
    )

    assert out_fees == fees
    assert out_filters == filters


class Item(NamedTuple):
    time: int


async def test_memory_store_overlapping_time_series(memory: storages.Memory) -> None:
    await memory.store_time_series_and_span('shard', 'key', [Item(0), Item(1)], 0, 2)
    await memory.store_time_series_and_span('shard', 'key', [Item(0), Item(1), Item(2)], 0, 3)

    time_spans = await list_async(memory.stream_time_series_spans('shard', 'key'))
    assert time_spans == [(0, 3)]

    items = await list_async(memory.stream_time_series('shard', 'key', Item))
    assert items == [Item(0), Item(1), Item(2)]


async def test_memory_store_overlapping_time_series_concurrently(memory: storages.Memory) -> None:
    # Chaos.
    NUM_SPANS = 100
    spans = [(random.randrange(0, 10), random.randrange(10, 21)) for _ in range(NUM_SPANS)]
    min_start = min(s for s, _ in spans)
    max_end = max(e for _, e in spans)

    tasks = []
    for start, end in spans:
        tasks.append(memory.store_time_series_and_span(
            'shard', 'key', [Item(i) for i in range(start, end)], start, end
        ))
    await asyncio.gather(*tasks)

    time_spans = await list_async(memory.stream_time_series_spans('shard', 'key'))
    assert min(start for start, _end in time_spans) == min_start
    assert max(end for _start, end in time_spans) == max_end

    items = await list_async(memory.stream_time_series('shard', 'key', Item))
    assert items == [Item(i) for i in range(min_start, max_end)]


class Abstract(ABC):
    @property
    @abstractmethod
    def value(self) -> int:
        return 0


class Concrete(Abstract):
    @property
    def value(self) -> int:
        return 1


@dataclass
class UnionTypeA:
    value: int = 1


@dataclass
class UnionTypeB:
    value: int = 2


@dataclass
class Container:
    abstract: Abstract
    union: Union[UnionTypeA, UnionTypeB]
    any_: Any
    optional: Optional[Abstract]


async def test_memory_get_set_dynamic_types(storage: storages.Storage) -> None:
    input_ = Container(
        abstract=Concrete(),
        union=UnionTypeB(),
        any_=Container(
            abstract=Concrete(),
            union=UnionTypeB(),
            any_=None,
            optional=None,
        ),
        optional=Concrete(),
    )
    await storage.set('shard', 'key', input_)
    output = await storage.get('shard', 'key', Container)

    assert output
    assert isinstance(output.abstract, Concrete)
    assert output.abstract.value == 1
    assert isinstance(output.union, UnionTypeB)
    assert output.union.value == 2
    assert output.any_
    assert isinstance(output.any_, Container)
    assert isinstance(output.any_.abstract, Concrete)
    assert output.any_.abstract.value == 1
    assert isinstance(output.any_.union, UnionTypeB)
    assert output.any_.union.value == 2
    assert not output.any_.any_
    assert output.optional
    assert isinstance(output.optional, Concrete)
    assert output.optional.value == 1
