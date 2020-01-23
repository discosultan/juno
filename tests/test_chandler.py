import asyncio
from decimal import Decimal

import pytest

from juno import Candle, JunoException, Trade
from juno.asyncio import cancel, cancelable, list_async
from juno.components import Chandler

from . import fakes


@pytest.mark.parametrize(
    'start,end,closed,efrom,eto,espans',
    [
        [0, 3, True, 0, 2, [(0, 2), (2, 3)]],  # Skips skipped candle at the end.
        [2, 3, True, 0, 0, [(2, 3)]],  # Empty if only skipped candle.
        [3, 5, True, 2, 5, [(3, 5)]],  # Filters out closed candle.
        [0, 5, False, 0, 5, [(0, 2), (2, 5)]],  # Includes closed candle.
        [0, 6, True, 0, 6, [(0, 2), (2, 5), (5, 6)]],  # Includes future candle.
        [5, 6, False, 5, 6, [(5, 6)]],  # Only future candle.
    ]
)
async def test_stream_candles(storage, start, end, closed, efrom, eto, espans):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
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
    )
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE
    )

    output_candles = await list_async(
        chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end, closed)
    )
    storage_key = (EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Candle, start, end)),
        list_async(storage.stream_time_series(storage_key, Candle, start, end)),
    )

    assert output_candles == expected_candles
    assert stored_candles == [c for c in output_candles if c.closed]
    assert stored_spans == espans


async def test_stream_future_candles_span_stored_until_stopped(storage):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    INTERVAL = 1
    START = 0
    CANCEL_AT = 5
    END = 10
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(future_candles=candles)
    time = fakes.Time(START, increment=1)
    chandler = Chandler(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time
    )

    task = asyncio.create_task(cancelable(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, START, END))
    ))
    await exchange.candle_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    storage_key = (EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Candle, START, END)),
        list_async(storage.stream_time_series(storage_key, Candle, START, END)),
    )

    assert stored_candles == candles
    assert stored_spans == [(START, candles[-1].time + INTERVAL)]


async def test_stream_candles_construct_from_trades(storage):
    exchange = fakes.Exchange()
    exchange.can_stream_historical_candles = False
    exchange.can_stream_candles = False

    trades = fakes.Trades(trades=[
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('4.0'), size=Decimal('1.0')),
        Trade(time=3, price=Decimal('2.0'), size=Decimal('2.0')),
    ])
    chandler = Chandler(
        trades=trades,
        storage=storage,
        exchanges=[exchange]
    )

    output_candles = await list_async(chandler.stream_candles('exchange', 'eth-btc', 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal('1.0'),
            high=Decimal('4.0'),
            low=Decimal('1.0'),
            close=Decimal('2.0'),
            volume=Decimal('4.0'),
            closed=True
        )
    ]


async def test_stream_candles_cancel_does_not_store_twice(storage):
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(historical_candles=candles)
    chandler = Chandler(storage=storage, exchanges=[exchange], storage_batch_size=1)

    stream_candles_task = asyncio.create_task(
        cancelable(list_async(chandler.stream_candles('exchange', 'eth-btc', 1, 0, 2)))
    )

    await storage.stored_time_series_and_span.wait()
    await cancel(stream_candles_task)

    stored_candles = await list_async(
        storage.stream_time_series(('exchange', 'eth-btc', 1), Candle, 0, 2)
    )
    assert stored_candles == candles


async def test_stream_candles_on_ws_disconnect(storage):
    time = fakes.Time(0)
    exchange = fakes.Exchange(future_candles=[
        Candle(time=0),
        Candle(time=1),
    ])
    chandler = Chandler(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles('exchange', 'eth-btc', 1, 0, 5))
    )
    await exchange.candle_queue.join()

    time.time = 3
    exchange.historical_candles = [
        Candle(time=0),
        Candle(time=1),
        Candle(time=2),
    ]
    for exc_or_candle in [JunoException(), Candle(time=3)]:
        exchange.candle_queue.put_nowait(exc_or_candle)
    await exchange.candle_queue.join()

    time.time = 5
    for exc_or_candle in [Candle(time=4), Candle(time=5)]:
        exchange.candle_queue.put_nowait(exc_or_candle)

    result = await stream_candles_task

    assert len(result) == 5
    for i, candle in enumerate(result):
        assert candle.time == i


async def test_stream_candles_fill_missing_with_last(storage):
    exchange = fakes.Exchange(historical_candles=[
        Candle(time=0, close=1),
        # Missed candle.
        Candle(time=2, close=2),
    ])
    chandler = Chandler(storage=storage, exchanges=[exchange])
    output = await list_async(
        chandler.stream_candles('exchange', 'eth-btc', 1, 0, 3, fill_missing_with_last=True)
    )
    assert output == [
        Candle(time=0, close=1),
        Candle(time=1, close=1),
        Candle(time=2, close=2),
    ]


async def test_stream_candles_construct_from_trades_if_interval_not_supported(storage):
    exchange = fakes.Exchange()
    exchange.can_stream_historical_candles = True

    informant = fakes.Informant(candle_intervals=[1])
    trades = fakes.Trades(trades=[
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('4.0'), size=Decimal('1.0')),
        Trade(time=3, price=Decimal('2.0'), size=Decimal('2.0')),
    ])
    chandler = Chandler(
        informant=informant,
        trades=trades,
        storage=storage,
        exchanges=[exchange]
    )

    output_candles = await list_async(chandler.stream_candles('exchange', 'eth-btc', 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal('1.0'),
            high=Decimal('4.0'),
            low=Decimal('1.0'),
            close=Decimal('2.0'),
            volume=Decimal('4.0'),
            closed=True
        )
    ]