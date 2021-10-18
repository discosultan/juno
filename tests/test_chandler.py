import asyncio
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from juno import Candle, ExchangeException, Trade
from juno.asyncio import cancel, list_async, resolved_stream
from juno.components import Chandler
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import WEEK_MS, strptimestamp
from juno.utils import key

from . import fakes


@pytest.mark.parametrize(
    "start,end,closed,efrom,eto,espans",
    [
        [0, 3, True, 0, 2, [(0, 3)]],  # Skips skipped candle at the end.
        [2, 3, True, 0, 0, [(2, 3)]],  # Empty if only skipped candle.
        [3, 5, True, 2, 5, [(3, 5)]],  # Filters out closed candle.
        [0, 5, False, 0, 5, [(0, 5)]],  # Includes closed candle.
        [0, 6, True, 0, 6, [(0, 6)]],  # Includes future candle.
        [5, 6, False, 5, 6, [(5, 6)]],  # Only future candle.
    ],
)
async def test_stream_candles(
    storage: fakes.Storage, start, end, closed, efrom, eto, espans
) -> None:
    EXCHANGE = "exchange"
    SYMBOL = "eth-btc"
    INTERVAL = 1
    CURRENT = 5
    STORAGE_BATCH_SIZE = 2
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
    time = fakes.Time(CURRENT, increment=1)
    exchange = fakes.Exchange(
        historical_candles=historical_candles,
        future_candles=future_candles,
        candle_intervals={1: 0},
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE,
    )

    output_candles = await list_async(
        chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end, closed)
    )
    shard = key(EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "candle", start, end)),
        list_async(storage.stream_time_series(shard, "candle", Candle, start, end)),
    )

    assert output_candles == expected_candles
    assert stored_candles == [c for c in output_candles if c.closed]
    assert stored_spans == espans


async def test_stream_future_candles_span_stored_until_cancelled(storage: fakes.Storage) -> None:
    EXCHANGE = "exchange"
    SYMBOL = "eth-btc"
    INTERVAL = 1
    START = 0
    CANCEL_AT = 5
    END = 10
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(future_candles=candles, candle_intervals={INTERVAL: 0})
    time = fakes.Time(START, increment=1)
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    task = asyncio.create_task(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, START, END))
    )
    await exchange.candle_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    shard = key(EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "candle", START, END)),
        list_async(storage.stream_time_series(shard, "candle", Candle, START, END)),
    )

    assert stored_candles == candles
    assert stored_spans == [(START, candles[-1].time + INTERVAL)]


async def test_stream_candles_construct_from_trades(storage: Storage) -> None:
    exchange = fakes.Exchange(candle_intervals={5: 0})
    exchange.can_stream_historical_candles = False
    exchange.can_stream_candles = False

    trades = fakes.Trades(
        trades=[
            Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
            Trade(time=1, price=Decimal("4.0"), size=Decimal("1.0")),
            Trade(time=3, price=Decimal("2.0"), size=Decimal("2.0")),
        ]
    )
    chandler = Chandler(trades=trades, storage=storage, exchanges=[exchange])

    output_candles = await list_async(chandler.stream_candles("exchange", "eth-btc", 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal("1.0"),
            high=Decimal("4.0"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("4.0"),
            closed=True,
        )
    ]


async def test_stream_candles_cancel_does_not_store_twice(storage: fakes.Storage) -> None:
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(historical_candles=candles, candle_intervals={1: 0})
    chandler = Chandler(storage=storage, exchanges=[exchange], storage_batch_size=1)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles("exchange", "eth-btc", 1, 0, 2))
    )

    await storage.stored_time_series_and_span.wait()
    await cancel(stream_candles_task)

    stored_candles = await list_async(
        storage.stream_time_series(key("exchange", "eth-btc", 1), "candle", Candle, 0, 2)
    )
    assert stored_candles == candles


async def test_stream_candles_on_exchange_exception(storage: fakes.Storage) -> None:
    time = fakes.Time(0)
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
        future_candles=[
            Candle(time=0),
            Candle(time=1),
        ],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles("exchange", "eth-btc", 1, 0, 5))
    )
    await exchange.candle_queue.join()

    time.time = 3
    exchange.historical_candles = [
        Candle(time=0),
        Candle(time=1),
        Candle(time=2),
    ]
    for exc_or_candle in [ExchangeException(), Candle(time=3)]:
        exchange.candle_queue.put_nowait(exc_or_candle)
    await exchange.candle_queue.join()

    time.time = 5
    for exc_or_candle in [Candle(time=4), Candle(time=5)]:
        exchange.candle_queue.put_nowait(exc_or_candle)

    result = await stream_candles_task

    assert len(result) == 5
    for i, candle in enumerate(result):
        assert candle.time == i


async def test_stream_candles_on_exchange_exception_and_cancelled(storage: fakes.Storage) -> None:
    time = fakes.Time(0)
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
        future_candles=[
            Candle(time=0),
        ],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles("exchange", "eth-btc", 1, 0, 4))
    )
    await exchange.candle_queue.join()

    time.time = 2
    exchange.historical_candles = [
        Candle(time=0),
        Candle(time=1),
    ]
    for exc_or_candle in [ExchangeException(), Candle(time=2)]:
        exchange.candle_queue.put_nowait(exc_or_candle)
    await exchange.candle_queue.join()

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


async def test_stream_candles_fill_missing_with_last(storage: fakes.Storage) -> None:
    first_candle = Candle(
        time=1,
        open=Decimal("1.0"),
        high=Decimal("3.0"),
        low=Decimal("0.0"),
        close=Decimal("2.0"),
    )
    third_candle = Candle(
        time=3,
        open=Decimal("2.0"),
        high=Decimal("4.0"),
        low=Decimal("1.0"),
        close=Decimal("3.0"),
    )
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
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
            exchange="exchange",
            symbol="eth-btc",
            interval=1,
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
            open=Decimal("2.0"),
            high=Decimal("2.0"),
            low=Decimal("2.0"),
            close=Decimal("2.0"),
        ),
        third_candle,
    ]


async def test_stream_candles_construct_from_trades_if_interval_not_supported(
    storage: fakes.Storage,
) -> None:
    exchange = fakes.Exchange(candle_intervals={1: 0})
    exchange.can_stream_historical_candles = True

    trades = fakes.Trades(
        trades=[
            Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
            Trade(time=1, price=Decimal("4.0"), size=Decimal("1.0")),
            Trade(time=3, price=Decimal("2.0"), size=Decimal("2.0")),
        ]
    )
    chandler = Chandler(trades=trades, storage=storage, exchanges=[exchange])

    output_candles = await list_async(chandler.stream_candles("exchange", "eth-btc", 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal("1.0"),
            high=Decimal("4.0"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("4.0"),
            closed=True,
        )
    ]


async def test_stream_candles_no_duplicates_if_same_candle_from_rest_and_websocket(
    storage,
) -> None:
    time = fakes.Time(1)
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
        historical_candles=[Candle(time=0)],
        future_candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    count = 0
    async for candle in chandler.stream_candles("exchange", "eth-btc", 1, 0, 2):
        time.time = candle.time + 1
        count += 1
    assert count == 2


async def test_stream_historical_candles_bad_time_adjust_to_previous(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=3)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles("exchange", "eth-btc", 2, 0, 4))

    assert candles == [Candle(time=0), Candle(time=2)]


async def test_stream_historical_candles_bad_time_skip_when_no_volume(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=1, volume=Decimal("0.0"))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(chandler.stream_candles("exchange", "eth-btc", 2, 0, 4))

    assert candles == [Candle(time=0)]


async def test_stream_historical_candles_bad_time_error_when_unadjustable(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=1, volume=Decimal("1.0"))],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    with pytest.raises(RuntimeError):
        async for _candle in chandler.stream_candles("exchange", "eth-btc", 2, 0, 4):
            pass


async def test_stream_historical_candles_do_not_adjust_over_daily_interval(storage) -> None:
    start = strptimestamp("2019-12-26")
    end = strptimestamp("2020-01-02")
    exchange = fakes.Exchange(
        candle_intervals={WEEK_MS: 0},
        historical_candles=[Candle(time=start)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await list_async(
        chandler.stream_candles(
            "exchange",
            "eth-btc",
            WEEK_MS,
            start,
            end,
        )
    )

    assert candles == [Candle(time=start)]


@pytest.mark.parametrize(
    "earliest_exchange_start,time",
    [
        (10, 20),  # Simple happy flow.
        (0, 16),  # `final_end` and start not being over-adjusted.
    ],
)
async def test_get_first_candle_by_search(storage, earliest_exchange_start, time) -> None:
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    exchange = fakes.Exchange(
        candle_intervals={2: 0},
        historical_candles=candles,
    )
    exchange.can_stream_historical_earliest_candle = False
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start,
    )

    first_candle = await chandler.get_first_candle("exchange", "eth-btc", 2)

    assert first_candle.time == 12


@pytest.mark.parametrize(
    "earliest_exchange_start,time",
    [
        (1, 2),  # No candles
        (0, 1),  # Single last candle.
    ],
)
async def test_get_first_candle_by_search_not_found(
    storage, earliest_exchange_start, time
) -> None:
    exchange = fakes.Exchange(historical_candles=[Candle(time=0)])
    exchange.can_stream_historical_earliest_candle = False
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start,
    )

    with pytest.raises(ValueError):
        await chandler.get_first_candle("exchange", "eth-btc", 1)


async def test_get_first_candle_caching_to_storage(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
        historical_candles=[Candle(time=0)],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        earliest_exchange_start=0,
    )

    await chandler.get_first_candle("exchange", "eth-btc", 1)

    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    await chandler.get_first_candle("exchange", "eth-btc", 1)

    assert len(storage.get_calls) == 2
    assert len(storage.set_calls) == 1


async def test_get_last_candle(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={2: 0},
        historical_candles=[Candle(time=0), Candle(time=2)],
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(4).get_time,
    )

    candle = await chandler.get_last_candle("exchange", "eth-btc", 2)

    assert candle.time == 2


async def test_list_candles(storage) -> None:
    exchange = fakes.Exchange(
        candle_intervals={1: 0},
        historical_candles=[Candle(time=0), Candle(time=1)],
    )
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.list_candles("exchange", "eth-btc", 1, 0, 2)

    assert len(candles) == 2


async def test_map_symbol_interval_candles(storage, mocker: MockerFixture) -> None:
    exchange = mocker.MagicMock(Exchange, autospec=True)
    exchange.list_candle_intervals.return_value = [
        1,
        2,
    ]

    def stream_historical_candles_side_effect(symbol, interval, start, end):
        if interval == 1:
            return resolved_stream(*[Candle(time=0), Candle(time=1)])
        else:  # 2
            return resolved_stream(*[Candle(time=0)])

    exchange.stream_historical_candles.side_effect = stream_historical_candles_side_effect
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.map_symbol_interval_candles(
        "magicmock", ["eth-btc", "ltc-btc"], [1, 2], 0, 2
    )

    assert len(candles) == 4


async def test_list_candles_simulate_open_from_interval(mocker: MockerFixture, storage) -> None:
    async def stream_historical_candles(symbol, interval, start, end):
        if interval == 1:
            for i in range(6):
                yield Candle(
                    time=i,
                    open=Decimal(f"{i}.0"),
                    high=Decimal(f"{i + 1}.0"),
                    low=Decimal(f"{i}.0"),
                    close=Decimal(f"{i + 1}.0"),
                    volume=Decimal("1.0"),
                    closed=True,
                )
        else:  # interval == 2
            for i in range(3):
                yield Candle(
                    time=i * 2,
                    open=Decimal(f"{i * 2}.0"),
                    high=Decimal(f"{(i + 1) * 2}.0"),
                    low=Decimal(f"{i * 2}.0"),
                    close=Decimal(f"{(i + 1) * 2}.0"),
                    volume=Decimal("2.0"),
                )

    exchange = mocker.MagicMock(Exchange, autospec=True)
    exchange.list_candle_intervals.return_value = [
        1,
        2,
    ]
    exchange.stream_historical_candles.side_effect = stream_historical_candles
    chandler = Chandler(storage=storage, exchanges=[exchange])

    candles = await chandler.list_candles(
        exchange="magicmock",
        symbol="eth-btc",
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
            open=Decimal(f"{i - i % 2}.0"),
            high=Decimal(f"{i + 1}.0"),
            low=Decimal(f"{i - i % 2}.0"),
            close=Decimal(f"{i + 1}.0"),
            volume=Decimal(f"{i % 2 + 1}.0"),
            closed=False if i % 2 == 0 else True,
        )
        for i in range(6)
    ]
    assert candles == expected_candles


@pytest.mark.parametrize(
    "intervals,patterns,expected_output",
    [
        ([1, 2], None, [1, 2]),
        ([1, 2, 3], [1, 2], [1, 2]),
    ],
)
async def test_list_candle_intervals(storage, intervals, patterns, expected_output) -> None:
    exchange = fakes.Exchange(candle_intervals=intervals)

    async with Chandler(storage=storage, exchanges=[exchange]) as chandler:
        output = chandler.list_candle_intervals("exchange", patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)
