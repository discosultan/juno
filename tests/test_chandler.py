import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Optional

import pytest
from asyncstdlib import list as list_async
from pytest_mock import MockerFixture

from juno import (
    Candle,
    ExchangeException,
    Interval,
    Interval_,
    Symbol,
    Timestamp,
    Timestamp_,
    Trade,
)
from juno.asyncio import cancel, resolved_stream
from juno.components import Chandler
from juno.storages import Storage
from tests.mocks import mock_exchange, mock_stream_values, mock_trades

from . import fakes


@pytest.mark.parametrize(
    "start,end,historical_candles,future_candles,expected_spans",
    [
        # Skips skipped candle at the end.
        [0, 3, [Candle(time=0), Candle(time=1)], [], [(0, 3)]],
        # Empty if only skipped candle.
        [2, 3, [], [], [(2, 3)]],
        [3, 5, [Candle(time=3), Candle(time=4)], [], [(3, 5)]],
        [0, 5, [Candle(time=0), Candle(time=1), Candle(time=3), Candle(time=4)], [], [(0, 5)]],
        # Includes future candle.
        [
            0,
            6,
            [Candle(time=0), Candle(time=1), Candle(time=3), Candle(time=4)],
            [Candle(time=5)],
            [(0, 6)],
        ],
        # Only future candle.
        [5, 6, [], [Candle(time=5)], [(5, 6)]],
    ],
)
async def test_stream_candles(
    mocker: MockerFixture,
    storage: fakes.Storage,
    start: Timestamp,
    end: Timestamp,
    historical_candles: list[Candle],
    future_candles: list[Candle],
    expected_spans: list[tuple[Timestamp, Timestamp]],
) -> None:
    SYMBOL = "eth-btc"
    INTERVAL = 1
    CURRENT = 5
    STORAGE_BATCH_SIZE = 2
    # historical_candles = [
    #     Candle(time=0),
    #     Candle(time=1),
    #     # Deliberately skipped candle.
    #     Candle(time=3),
    #     Candle(time=4),
    # ]
    # future_candles = [
    #     Candle(time=5),
    # ]
    time = fakes.Time(CURRENT, increment=1)
    exchange = mock_exchange(
        mocker,
        candles=historical_candles,
        stream_candles=future_candles,
        candle_intervals=[INTERVAL],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE,
    )

    output_candles = await list_async(
        chandler.stream_candles(
            exchange=exchange.name,
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
        )
    )
    shard = Storage.key(exchange.name, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "candle", start, end)),
        list_async(storage.stream_time_series(shard, "candle", Candle, start, end)),
    )

    expected_candles = historical_candles + future_candles
    assert output_candles == expected_candles
    assert stored_candles == expected_candles
    assert stored_spans == expected_spans


async def test_stream_future_candles_span_stored_until_cancelled(
    mocker: MockerFixture, storage: fakes.Storage
) -> None:
    SYMBOL = "eth-btc"
    INTERVAL = 1
    START = 0
    CANCEL_AT = 5
    END = 10
    candles = [Candle(time=1)]
    exchange = mock_exchange(mocker, stream_candles=candles, candle_intervals=[INTERVAL])
    time = fakes.Time(START, increment=1)
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    task = asyncio.create_task(
        list_async(chandler.stream_candles(exchange.name, SYMBOL, INTERVAL, START, END))
    )
    await exchange.stream_candles_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    shard = Storage.key(exchange.name, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "candle", START, END)),
        list_async(storage.stream_time_series(shard, "candle", Candle, START, END)),
    )

    assert stored_candles == candles
    assert stored_spans == [(START, candles[-1].time + INTERVAL)]


async def test_stream_candles_construct_from_trades(
    mocker: MockerFixture, storage: Storage
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[5],
        can_stream_historical_candles=False,
        can_stream_candles=False,
    )

    trades = mock_trades(
        mocker,
        trades=[
            Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
            Trade(time=1, price=Decimal("4.0"), size=Decimal("1.0")),
            Trade(time=3, price=Decimal("2.0"), size=Decimal("2.0")),
        ],
    )
    chandler = Chandler(trades=trades, storage=storage, exchanges=[exchange])

    output_candles = await list_async(chandler.stream_candles(exchange.name, "eth-btc", 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal("1.0"),
            high=Decimal("4.0"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("4.0"),
        )
    ]


async def test_stream_candles_cancel_does_not_store_twice(
    mocker: MockerFixture, storage: fakes.Storage
) -> None:
    candles = [Candle(time=1)]
    exchange = mock_exchange(mocker, candles=candles, candle_intervals=[1])
    chandler = Chandler(storage=storage, exchanges=[exchange], storage_batch_size=1)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(exchange.name, "eth-btc", 1, 0, 2))
    )

    await storage.stored_time_series_and_span.wait()
    await cancel(stream_candles_task)

    stored_candles = await list_async(
        storage.stream_time_series(
            Storage.key(exchange.name, "eth-btc", 1), "candle", Candle, 0, 2
        )
    )
    assert stored_candles == candles


async def test_stream_candles_on_exchange_exception(
    mocker: MockerFixture, storage: fakes.Storage
) -> None:
    time = fakes.Time(0)
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        stream_candles=[
            Candle(time=0),
            Candle(time=1),
        ],
    )

    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(exchange.name, "eth-btc", 1, 0, 5))
    )
    await exchange.stream_candles_queue.join()

    time.time = 3
    exchange.stream_historical_candles.side_effect = mock_stream_values(
        Candle(time=2),
    )
    for exc_or_candle in [ExchangeException(), Candle(time=3)]:
        exchange.stream_candles_queue.put_nowait(exc_or_candle)
    await exchange.stream_candles_queue.join()

    time.time = 5
    for candle in [Candle(time=4), Candle(time=5)]:
        exchange.stream_candles_queue.put_nowait(candle)

    result = await stream_candles_task

    assert len(result) == 5
    for i, candle in enumerate(result):
        assert candle.time == i


async def test_stream_candles_on_exchange_exception_and_cancelled(
    mocker: MockerFixture, storage: fakes.Storage
) -> None:
    time = fakes.Time(0)
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        stream_candles=[
            Candle(time=0),
        ],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles(exchange.name, "eth-btc", 1, 0, 4))
    )
    await exchange.stream_candles_queue.join()

    time.time = 2
    exchange.stream_historical_candles.side_effect = mock_stream_values(
        Candle(time=1),
    )
    for exc_or_candle in [ExchangeException(), Candle(time=2)]:
        exchange.stream_candles_queue.put_nowait(exc_or_candle)
    await exchange.stream_candles_queue.join()

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


@pytest.mark.parametrize(
    "input,expected_output",
    [
        (
            [
                # Missed candle.
                Candle(
                    time=1,
                    open=Decimal("1.0"),
                    high=Decimal("3.0"),
                    low=Decimal("0.0"),
                    close=Decimal("2.0"),
                ),
                # Missed candle.
                Candle(
                    time=3,
                    open=Decimal("2.0"),
                    high=Decimal("4.0"),
                    low=Decimal("1.0"),
                    close=Decimal("3.0"),
                ),
                # Missed candle.
            ],
            [
                None,
                Candle(
                    time=1,
                    open=Decimal("1.0"),
                    high=Decimal("3.0"),
                    low=Decimal("0.0"),
                    close=Decimal("2.0"),
                ),
                None,
                Candle(
                    time=3,
                    open=Decimal("2.0"),
                    high=Decimal("4.0"),
                    low=Decimal("1.0"),
                    close=Decimal("3.0"),
                ),
                None,
            ],
        ),
        (
            [
                # Missed candle.
                # Missed candle.
                # Missed candle.
                # Missed candle.
                # Missed candle.
            ],
            [
                None,
                None,
                None,
                None,
                None,
            ],
        ),
    ],
)
async def test_stream_candles_fill_missing_with_none(
    mocker: MockerFixture,
    storage: fakes.Storage,
    input: list[Candle],
    expected_output: list[Optional[Candle]],
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        candles=input,
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])
    output = await list_async(
        chandler.stream_candles_fill_missing_with_none(
            exchange=exchange.name,
            symbol="eth-btc",
            interval=1,
            start=0,
            end=5,
        )
    )
    assert output == expected_output


async def test_stream_candles_construct_from_trades_if_interval_not_supported(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(mocker, candle_intervals=[1], can_stream_historical_candles=True)

    trades = mock_trades(
        mocker,
        trades=[
            Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
            Trade(time=1, price=Decimal("4.0"), size=Decimal("1.0")),
            Trade(time=3, price=Decimal("2.0"), size=Decimal("2.0")),
        ],
    )
    chandler = Chandler(trades=trades, storage=storage, exchanges=[exchange])

    output_candles = await list_async(chandler.stream_candles(exchange.name, "eth-btc", 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal("1.0"),
            high=Decimal("4.0"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("4.0"),
        )
    ]


async def test_stream_candles_no_duplicates_if_same_candle_from_rest_and_websocket(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    time = fakes.Time(1)
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        candles=[Candle(time=0)],
        stream_candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    count = 0
    async for candle in chandler.stream_candles(exchange.name, "eth-btc", 1, 0, 2):
        time.time = candle.time + 1
        count += 1
    assert count == 2


async def test_stream_historical_candles_bad_time_adjust_to_previous(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[2],
        candles=[Candle(time=0), Candle(time=3)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles(exchange.name, "eth-btc", 2, 0, 4))

    assert candles == [Candle(time=0), Candle(time=2)]


async def test_stream_historical_candles_bad_time_skip_when_no_volume(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[2],
        candles=[Candle(time=0), Candle(time=1, volume=Decimal("0.0"))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles(exchange.name, "eth-btc", 2, 0, 4))

    assert candles == [Candle(time=0)]


async def test_stream_historical_candles_bad_time_error_when_unadjustable(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[2],
        candles=[Candle(time=0), Candle(time=1, volume=Decimal("1.0"))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    with pytest.raises(RuntimeError):
        async for _ in chandler.stream_candles(exchange.name, "eth-btc", 2, 0, 4):
            pass


async def test_stream_historical_candles_do_not_adjust_over_daily_interval(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    start = Timestamp_.parse("2019-12-26")
    end = Timestamp_.parse("2020-01-02")
    exchange = mock_exchange(
        mocker,
        candle_intervals=[Interval_.WEEK],
        candles=[Candle(time=start)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(
        chandler.stream_candles(
            exchange.name,
            "eth-btc",
            Interval_.WEEK,
            start,
            end,
        )
    )

    assert candles == [Candle(time=start)]


@pytest.mark.parametrize(
    "earliest_exchange_start,time",
    [
        # Simple happy flow.
        (10, 20),
        # `final_end` and start not being over-adjusted.
        (0, 16),
    ],
)
async def test_get_first_candle_by_search(
    mocker: MockerFixture,
    storage: fakes.Storage,
    earliest_exchange_start: Timestamp,
    time: Timestamp,
) -> None:
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    exchange = mock_exchange(
        mocker,
        candle_intervals=[2],
        can_stream_historical_earliest_candle=False,
    )

    async def stream_historical_candles(
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
    ):
        for candle in (candle for candle in candles if candle.time >= start and candle.time < end):
            yield candle

    exchange.stream_historical_candles.side_effect = stream_historical_candles
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        exchange_earliest_start=earliest_exchange_start,
    )

    first_candle = await chandler.get_first_candle(exchange.name, "eth-btc", 2)

    assert first_candle.time == 12


@pytest.mark.parametrize(
    "earliest_exchange_start,time",
    [
        (1, 2),  # No candles
        (0, 1),  # Single last candle.
    ],
)
async def test_get_first_candle_by_search_not_found(
    mocker: MockerFixture,
    storage: fakes.Storage,
    earliest_exchange_start: Timestamp,
    time: Timestamp,
) -> None:
    exchange = mock_exchange(
        mocker,
        candles=[Candle(time=0)],
        can_stream_historical_earliest_candle=False,
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        exchange_earliest_start=earliest_exchange_start,
    )

    with pytest.raises(ValueError):
        await chandler.get_first_candle(exchange.name, "eth-btc", 1)


async def test_get_first_candle_caching_to_storage(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        candles=[Candle(time=0)],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        exchange_earliest_start=0,
    )

    await chandler.get_first_candle(exchange.name, "eth-btc", 1)

    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    await chandler.get_first_candle(exchange.name, "eth-btc", 1)

    assert len(storage.get_calls) == 2
    assert len(storage.set_calls) == 1


async def test_get_last_candle(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[2],
        candles=[Candle(time=2)],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(4).get_time,
    )

    candle = await chandler.get_last_candle(exchange.name, "eth-btc", 2)

    assert candle.time == 2
    exchange.stream_historical_candles.assert_called_once_with(
        symbol="eth-btc",
        interval=2,
        start=2,
        end=4,
    )


async def test_list_candles(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1],
        candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.list_candles(exchange.name, "eth-btc", 1, 0, 2)

    assert len(candles) == 2


async def test_map_symbol_interval_candles(storage: fakes.Storage, mocker: MockerFixture) -> None:
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1, 2],
    )

    def stream_historical_candles_side_effect(symbol, interval, start, end):
        if interval == 1:
            return resolved_stream(*[Candle(time=0), Candle(time=1)])
        else:  # 2
            return resolved_stream(*[Candle(time=0)])

    exchange.stream_historical_candles.side_effect = stream_historical_candles_side_effect
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.map_symbol_interval_candles(
        exchange.name, ["eth-btc", "ltc-btc"], [1, 2], 0, 2
    )

    assert len(candles) == 4


@pytest.mark.parametrize(
    "intervals,patterns,expected_output",
    [
        ([1, 2], None, [1, 2]),
        ([1, 2, 3], [1, 2], [1, 2]),
    ],
)
async def test_list_candle_intervals(
    mocker: MockerFixture,
    storage: fakes.Storage,
    intervals: list[Interval],
    patterns: Optional[list[Interval]],
    expected_output: list[Interval],
) -> None:
    exchange = mock_exchange(mocker, candle_intervals=intervals)

    async with Chandler(storage=storage, exchanges=[exchange]) as chandler:
        output = chandler.list_candle_intervals(exchange.name, patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


async def test_stream_concurrent_historical_candles(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    time = fakes.Time(100)
    exchange = mock_exchange(
        mocker,
        candle_intervals=[1, 2],
        can_stream_historical_candles=True,
    )

    def stream_historical_candles(
        symbol: Symbol, interval: Interval, start: Timestamp, end: Timestamp
    ):
        if interval == 1:
            return resolved_stream(
                Candle(time=0, close=Decimal("1.0")),
                Candle(time=1, close=Decimal("1.0")),
                Candle(time=2, close=Decimal("1.0")),
                Candle(time=3, close=Decimal("1.0")),
            )
        elif interval == 2:
            return resolved_stream(
                Candle(time=0, close=Decimal("2.0")),
                Candle(time=2, close=Decimal("2.0")),
            )
        raise ValueError()

    exchange.stream_historical_candles.side_effect = stream_historical_candles
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
    )

    output = await list_async(
        chandler.stream_concurrent_candles(
            exchange=exchange.name,
            entries=[("eth-btc", 1, "regular"), ("eth-btc", 2, "regular")],
            start=0,
            end=4,
        )
    )

    assert output == [
        (Candle(time=0, close=Decimal("1.0")), ("eth-btc", 1, "regular")),  # time 1
        (Candle(time=0, close=Decimal("2.0")), ("eth-btc", 2, "regular")),  # time 2
        (Candle(time=1, close=Decimal("1.0")), ("eth-btc", 1, "regular")),  # time 2
        (Candle(time=2, close=Decimal("1.0")), ("eth-btc", 1, "regular")),  # time 3
        (Candle(time=2, close=Decimal("2.0")), ("eth-btc", 2, "regular")),  # time 4
        (Candle(time=3, close=Decimal("1.0")), ("eth-btc", 1, "regular")),  # time 4
    ]


async def test_stream_concurrent_historical_candles_with_offset_time(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    time = fakes.Time(Timestamp_.parse("2018-01-08"))
    exchange = mock_exchange(
        mocker,
        candle_intervals=[Interval_.DAY, Interval_.WEEK],
        can_stream_historical_candles=True,
    )

    def stream_historical_candles(
        symbol: Symbol, interval: Interval, start: Timestamp, end: Timestamp
    ):
        if interval == Interval_.DAY:
            return resolved_stream(
                Candle(time=Timestamp_.parse("2018-01-01"), close=Decimal("1.0")),  # Mon
                Candle(time=Timestamp_.parse("2018-01-02"), close=Decimal("1.0")),
                Candle(time=Timestamp_.parse("2018-01-03"), close=Decimal("1.0")),
                Candle(time=Timestamp_.parse("2018-01-04"), close=Decimal("1.0")),
                Candle(time=Timestamp_.parse("2018-01-05"), close=Decimal("1.0")),
                Candle(time=Timestamp_.parse("2018-01-06"), close=Decimal("1.0")),
                Candle(time=Timestamp_.parse("2018-01-07"), close=Decimal("1.0")),  # Sun
            )
        elif interval == Interval_.WEEK:
            return resolved_stream(
                Candle(time=Timestamp_.parse("2018-01-01"), close=Decimal("7.0")),
            )
        raise ValueError()

    exchange.stream_historical_candles.side_effect = stream_historical_candles
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
    )

    output = await list_async(
        chandler.stream_concurrent_candles(
            exchange=exchange.name,
            entries=[
                ("eth-btc", Interval_.DAY, "regular"),
                ("eth-btc", Interval_.WEEK, "regular"),
            ],
            start=Timestamp_.parse("2018-01-01"),
            end=Timestamp_.parse("2018-01-08"),
        )
    )

    assert output == [
        (
            Candle(time=Timestamp_.parse("2018-01-01"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-02"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-03"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-04"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-05"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-06"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-01"), close=Decimal("7.0")),
            ("eth-btc", Interval_.WEEK, "regular"),
        ),
        (
            Candle(time=Timestamp_.parse("2018-01-07"), close=Decimal("1.0")),
            ("eth-btc", Interval_.DAY, "regular"),
        ),
    ]


async def test_stream_concurrent_future_candles(
    mocker: MockerFixture,
    storage: fakes.Storage,
) -> None:
    time = fakes.Time(0)
    exchange = mock_exchange(
        mocker,
        candle_intervals=[3, 5],
        can_stream_candles=True,
    )

    @asynccontextmanager
    async def connect_stream_future_candles(symbol: Symbol, interval: Interval):
        def inner():
            if interval == 3:
                return resolved_stream(
                    Candle(time=0, close=Decimal("3.0")),
                    Candle(time=3, close=Decimal("3.0")),
                    Candle(time=6, close=Decimal("3.0")),
                )
            elif interval == 5:
                return resolved_stream(
                    Candle(time=0, close=Decimal("5.0")),
                    Candle(time=5, close=Decimal("5.0")),
                )
            raise ValueError()

        yield inner()

    exchange.connect_stream_candles.side_effect = connect_stream_future_candles
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
    )

    output = await list_async(
        chandler.stream_concurrent_candles(
            exchange=exchange.name,
            entries=[("eth-btc", 3, "regular"), ("eth-btc", 5, "regular")],
            start=0,
            end=10,
        )
    )

    assert output == [
        (Candle(time=0, close=Decimal("3.0")), ("eth-btc", 3, "regular")),
        (Candle(time=0, close=Decimal("5.0")), ("eth-btc", 5, "regular")),
        (Candle(time=3, close=Decimal("3.0")), ("eth-btc", 3, "regular")),
        (Candle(time=6, close=Decimal("3.0")), ("eth-btc", 3, "regular")),
        (Candle(time=5, close=Decimal("5.0")), ("eth-btc", 5, "regular")),
    ]
