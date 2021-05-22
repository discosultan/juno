import asyncio
from decimal import Decimal
from typing import AsyncIterable, Callable, Union

import pytest

from juno import ExchangeException
from juno.asyncio import cancel, create_queue, list_async, resolved_stream
from juno.candles import Candle, Chandler
from juno.storages import Storage
from juno.time import WEEK_MS, strptimestamp
from juno.trades import Trade
from juno.utils import key
from tests import fakes
from tests.trades.mock import mock_trades

from .mock import mock_exchange_candles

EXCHANGE = 'magicmock'
SYMBOL = 'eth-btc'
INTERVAL = 1
TIMEOUT = 1


def create_stream_candles(
    candles: list[Candle],
) -> Callable[[str, int, int, int], AsyncIterable[Candle]]:
    async def stream_candles(
        symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        for candle in candles:
            if candle.time >= start and candle.time < end:
                yield candle
    return stream_candles


@pytest.mark.parametrize(
    'start,end,closed,efrom,eto,espans',
    [
        [0, 3, True, 0, 2, [(0, 3)]],  # Skips skipped candle at the end.
        [2, 3, True, 0, 0, [(2, 3)]],  # Empty if only skipped candle.
        [3, 5, True, 2, 5, [(3, 5)]],  # Filters out closed candle.
        [0, 5, False, 0, 5, [(0, 5)]],  # Includes closed candle.
        [0, 6, True, 0, 6, [(0, 6)]],  # Includes future candle.
        [5, 6, False, 5, 6, [(5, 6)]],  # Only future candle.
    ]
)
async def test_stream_candles(
    storage: Storage, start, end, closed, efrom, eto, espans
) -> None:
    historical_candles = [
        Candle(time=0),
        Candle(time=1),
        # Deliberately skipped candle.
        Candle(time=3),
        Candle(time=4, closed=False),
        Candle(time=4),
    ]
    future_candles = [
        Candle(time=5),
    ]
    expected_candles = (historical_candles + future_candles)[efrom:eto]
    if closed:
        expected_candles = [c for c in expected_candles if c.closed]
    exchange = mock_exchange_candles(
        historical_candles=[c for c in historical_candles if c.time >= start and c.time < end],
        future_candles=future_candles,
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(5, increment=1).get_time,
        storage_batch_size=2,
    )

    output_candles = await list_async(
        chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end, closed)
    )
    shard = key(EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'candle', start, end)),
        list_async(storage.stream_time_series(shard, 'candle', Candle, start, end)),
    )

    assert output_candles == expected_candles
    assert stored_candles == [c for c in output_candles if c.closed]
    assert stored_spans == espans


async def test_stream_future_candles_span_stored_until_cancelled(storage: Storage) -> None:
    start = 0
    end = 10
    candles = [Candle(time=1)]
    candle_queue = create_queue(candles)
    time = fakes.Time(start, increment=1)
    exchange = mock_exchange_candles(future_candles=candle_queue)
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
    )

    task = asyncio.create_task(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end))
    )
    await asyncio.wait_for(candle_queue.join(), TIMEOUT)
    time.time = 5
    await cancel(task)

    shard = key(EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'candle', start, end)),
        list_async(storage.stream_time_series(shard, 'candle', Candle, start, end)),
    )

    assert stored_candles == candles
    assert stored_spans == [(start, candles[-1].time + INTERVAL)]


async def test_stream_candles_construct_from_trades(storage: Storage) -> None:
    trades = mock_trades([
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('4.0'), size=Decimal('1.0')),
        Trade(time=3, price=Decimal('2.0'), size=Decimal('2.0')),
    ])
    exchange = mock_exchange_candles(
        candle_intervals={5: 0},
        can_stream_candles=False,
        can_stream_historical_candles=False,
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        trades=trades,
    )

    output_candles = await list_async(chandler.stream_candles(EXCHANGE, SYMBOL, 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal('1.0'),
            high=Decimal('4.0'),
            low=Decimal('1.0'),
            close=Decimal('2.0'),
            volume=Decimal('4.0'),
            closed=True,
        )
    ]


async def test_stream_candles_cancel_does_not_store_twice(storage: fakes.Storage) -> None:
    candles = [Candle(time=1)]
    exchange = mock_exchange_candles(historical_candles=candles)
    chandler = Chandler(storage=storage, storage_batch_size=1, exchanges=[exchange])

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, 0, 2))
    )

    await storage.stored_time_series_and_span.wait()
    await cancel(stream_candles_task)

    stored_candles = await list_async(
        storage.stream_time_series(key(EXCHANGE, SYMBOL, INTERVAL), 'candle', Candle, 0, 2)
    )
    assert stored_candles == candles


async def test_stream_candles_on_exchange_exception(storage: Storage) -> None:
    time = fakes.Time(0)
    candles: asyncio.Queue[Union[Candle, ExchangeException]] = create_queue([
        Candle(time=0),
        Candle(time=1),
    ])
    exchange = mock_exchange_candles(future_candles=candles)
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
    )

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, 0, 5))
    )
    await asyncio.wait_for(candles.join(), TIMEOUT)

    time.time = 3
    exchange.stream_historical_candles.return_value = resolved_stream(Candle(time=2))
    candles.put_nowait(ExchangeException())
    candles.put_nowait(Candle(time=3))
    await asyncio.wait_for(candles.join(), TIMEOUT)

    time.time = 5
    candles.put_nowait(Candle(time=4))
    candles.put_nowait(Candle(time=5))  # Should not be taken from the queue.

    result = await stream_candles_task

    assert len(result) == 5
    for i, candle in enumerate(result):
        assert candle.time == i
    exchange.stream_historical_candles.assert_called_once_with(
        symbol=SYMBOL,
        interval=INTERVAL,
        start=2,
        end=3,
    )


async def test_stream_candles_on_exchange_exception_and_cancelled(storage: fakes.Storage) -> None:
    time = fakes.Time(0)
    candles: asyncio.Queue[Union[Candle, ExchangeException]] = create_queue([
        Candle(time=0),
    ])
    exchange = mock_exchange_candles(future_candles=candles)
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, 0, 4))
    )
    await asyncio.wait_for(candles.join(), TIMEOUT)

    time.time = 2
    exchange.stream_historical_candles.return_value = resolved_stream(
        Candle(time=1),
    )
    candles.put_nowait(ExchangeException())
    candles.put_nowait(Candle(time=2))
    await asyncio.wait_for(candles.join(), TIMEOUT)

    await cancel(stream_candles_task)

    assert len(storage.store_time_series_and_span_calls) == 2
    _, _, items1, start1, end1 = storage.store_time_series_and_span_calls[0]
    _, _, items2, start2, end2 = storage.store_time_series_and_span_calls[1]
    assert items1 == [Candle(time=0)]
    assert start1 == 0
    assert end1 == 1
    assert items2 == [Candle(time=1), Candle(time=2)]
    assert start2 == 1
    assert end2 == 3
    exchange.stream_historical_candles.assert_called_once_with(
        symbol=SYMBOL,
        interval=INTERVAL,
        start=1,
        end=2,
    )


async def test_stream_candles_fill_missing_with_last(storage: fakes.Storage) -> None:
    first_candle = Candle(
        time=1,
        open=Decimal('1.0'),
        high=Decimal('3.0'),
        low=Decimal('0.0'),
        close=Decimal('2.0'),
    )
    third_candle = Candle(
        time=3,
        open=Decimal('2.0'),
        high=Decimal('4.0'),
        low=Decimal('1.0'),
        close=Decimal('3.0'),
    )
    exchange = mock_exchange_candles(
        historical_candles=[
            # Missed candle should NOT get filled.
            first_candle,
            # Missed candle should get filled.
            third_candle,
        ],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])
    output = await list_async(
        chandler.stream_candles(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            interval=INTERVAL,
            start=0,
            end=4,
            fill_missing_with_last=True,
        )
    )
    assert output == [
        first_candle,
        Candle(
            time=2,
            # open=Decimal('1.0'),
            # high=Decimal('3.0'),
            # low=Decimal('0.0'),
            # close=Decimal('2.0'),
            open=Decimal('2.0'),
            high=Decimal('2.0'),
            low=Decimal('2.0'),
            close=Decimal('2.0'),
        ),
        third_candle,
    ]


async def test_stream_candles_construct_from_trades_if_interval_not_supported(
    storage: fakes.Storage
) -> None:
    trades = mock_trades([
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('4.0'), size=Decimal('1.0')),
        Trade(time=3, price=Decimal('2.0'), size=Decimal('2.0')),
    ])
    exchange = mock_exchange_candles(
        can_stream_historical_candles=True,
        candle_intervals={1: 0},
    )
    chandler = Chandler(
        trades=trades,
        storage=storage,
        exchanges=[exchange],
    )

    output_candles = await list_async(chandler.stream_candles(EXCHANGE, SYMBOL, 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal('1.0'),
            high=Decimal('4.0'),
            low=Decimal('1.0'),
            close=Decimal('2.0'),
            volume=Decimal('4.0'),
            closed=True,
        ),
    ]


async def test_stream_candles_no_duplicates_if_same_candle_from_rest_and_websocket(
    storage
) -> None:
    time = fakes.Time(1)
    exchange = mock_exchange_candles(
        historical_candles=[Candle(time=0)],
        future_candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    count = 0
    async for candle in chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, 0, 2):
        time.time = candle.time + 1
        count += 1
    assert count == 2


async def test_stream_historical_candles_bad_time_adjust_to_previous(storage) -> None:
    exchange = mock_exchange_candles(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=3)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles(EXCHANGE, SYMBOL, 2, 0, 4))

    assert candles == [Candle(time=0), Candle(time=2)]


async def test_stream_historical_candles_bad_time_skip_when_no_volume(storage) -> None:
    exchange = mock_exchange_candles(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=1, volume=Decimal('0.0'))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles(EXCHANGE, SYMBOL, 2, 0, 4))

    assert candles == [Candle(time=0)]


async def test_stream_historical_candles_bad_time_error_when_unadjustable(storage) -> None:
    exchange = mock_exchange_candles(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=1, volume=Decimal('1.0'))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    with pytest.raises(RuntimeError):
        async for _candle in chandler.stream_candles(EXCHANGE, SYMBOL, 2, 0, 4):
            pass


async def test_stream_historical_candles_do_not_adjust_over_daily_interval(storage) -> None:
    start = strptimestamp('2019-12-26')
    end = strptimestamp('2020-01-02')
    exchange = mock_exchange_candles(
        candle_intervals={WEEK_MS: 0},
        historical_candles=[Candle(time=start)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(
        chandler.stream_candles(
            EXCHANGE,
            SYMBOL,
            WEEK_MS,
            start,
            end,
        )
    )

    assert candles == [Candle(time=start)]


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (10, 20),  # Simple happy flow.
    (0, 16),  # `final_end` and start not being over-adjusted.
])
async def test_get_first_candle_by_search(storage, earliest_exchange_start, time) -> None:
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    exchange = mock_exchange_candles(
        can_stream_historical_earliest_candle=False,
        candle_intervals={2: 0},
    )

    exchange.stream_historical_candles.side_effect = create_stream_candles(candles)
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start,
    )

    first_candle = await chandler.get_first_candle(EXCHANGE, SYMBOL, 2)

    assert first_candle.time == 12


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (1, 2),  # No candles
    (0, 1),  # Single last candle.
])
async def test_get_first_candle_by_search_not_found(
    storage, earliest_exchange_start, time
) -> None:
    exchange = mock_exchange_candles(
        can_stream_historical_earliest_candle=False,
        historical_candles=[Candle(time=0)],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start,
    )

    with pytest.raises(ValueError):
        await chandler.get_first_candle(EXCHANGE, SYMBOL, INTERVAL)


async def test_get_first_candle_caching_to_storage(storage) -> None:
    exchange = mock_exchange_candles(historical_candles=[Candle()])
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        earliest_exchange_start=0,
    )

    await chandler.get_first_candle(EXCHANGE, SYMBOL, INTERVAL)

    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    await chandler.get_first_candle(EXCHANGE, SYMBOL, INTERVAL)

    assert len(storage.get_calls) == 2
    assert len(storage.set_calls) == 1


async def test_get_last_candle(storage) -> None:
    exchange = mock_exchange_candles()
    exchange.stream_historical_candles.side_effect = create_stream_candles(
        [Candle(time=0), Candle(time=2)]
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(4).get_time,
    )

    candle = await chandler.get_last_candle(EXCHANGE, SYMBOL, 2)

    assert candle.time == 2


async def test_list_candles(storage) -> None:
    exchange = mock_exchange_candles(
        historical_candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.list_candles(EXCHANGE, SYMBOL, INTERVAL, 0, 2)

    assert len(candles) == 2


async def test_map_symbol_interval_candles(storage, mocker) -> None:
    exchange = mock_exchange_candles(candle_intervals={
        1: 0,
        2: 0,
    })

    def stream_historical_candles_side_effect(symbol, interval, start, end):
        if interval == 1:
            return resolved_stream(*[Candle(time=0), Candle(time=1)])
        else:  # 2
            return resolved_stream(*[Candle(time=0)])

    exchange.stream_historical_candles.side_effect = (
        stream_historical_candles_side_effect
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.map_symbol_interval_candles(
        EXCHANGE, ['eth-btc', 'ltc-btc'], [1, 2], 0, 2
    )

    assert len(candles) == 4


async def test_list_candles_simulate_open_from_interval(mocker, storage) -> None:
    async def stream_historical_candles(symbol, interval, start, end):
        if interval == 1:
            for i in range(6):
                yield Candle(
                    time=i,
                    open=Decimal(f'{i}.0'),
                    high=Decimal(f'{i + 1}.0'),
                    low=Decimal(f'{i}.0'),
                    close=Decimal(f'{i + 1}.0'),
                    volume=Decimal('1.0'),
                    closed=True,
                )
        else:  # interval == 2
            for i in range(3):
                yield Candle(
                    time=i * 2,
                    open=Decimal(f'{i * 2}.0'),
                    high=Decimal(f'{(i + 1) * 2}.0'),
                    low=Decimal(f'{i * 2}.0'),
                    close=Decimal(f'{(i + 1) * 2}.0'),
                    volume=Decimal('2.0'),
                )

    exchange = mock_exchange_candles(
        candle_intervals={
            1: 0,
            2: 0,
        }
    )
    exchange.stream_historical_candles.side_effect = stream_historical_candles
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.list_candles(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        interval=2,
        start=0,
        end=6,
        simulate_open_from_interval=1,
        closed=True,
        fill_missing_with_last=True,
    )

    expected_candles = [
        Candle(
            time=i - i % 2,
            open=Decimal(f'{i - i % 2}.0'),
            high=Decimal(f'{i + 1}.0'),
            low=Decimal(f'{i - i % 2}.0'),
            close=Decimal(f'{i + 1}.0'),
            volume=Decimal(f'{i % 2 + 1}.0'),
            closed=False if i % 2 == 0 else True,
        ) for i in range(6)
    ]
    assert candles == expected_candles


@pytest.mark.parametrize('intervals,patterns,expected_output', [
    ([1, 2], None, [1, 2]),
    ([1, 2, 3], [1, 2], [1, 2]),
])
async def test_map_candle_intervals(storage, intervals, patterns, expected_output) -> None:
    exchange = mock_exchange_candles(candle_intervals={i: 0 for i in intervals})

    async with Chandler(storage=storage, exchanges=[exchange]) as chandler:
        output = chandler.map_candle_intervals(EXCHANGE, patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)
