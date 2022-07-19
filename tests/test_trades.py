import asyncio
from decimal import Decimal

import pytest
from asyncstdlib import list as list_async
from pytest_mock import MockerFixture

from juno import Timestamp, Trade
from juno.asyncio import cancel
from juno.components import Trades
from juno.storages import Storage
from tests import fakes
from tests.mocks import mock_exchange


async def test_stream_future_trades_span_stored_until_stopped(
    mocker: MockerFixture, storage: Storage
) -> None:
    SYMBOL = "eth-btc"
    START = 0
    CANCEL_AT = 5
    END = 10
    trades = [Trade(time=1)]
    exchange = mock_exchange(mocker, stream_trades=trades)
    time = fakes.Time(START, increment=1)
    trades_component = Trades(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    task = asyncio.create_task(
        list_async(trades_component.stream_trades(exchange.name, SYMBOL, START, END))
    )
    await exchange.stream_trades_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    shard = Storage.key(exchange.name, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "trade", START, END)),
        list_async(storage.stream_time_series(shard, "trade", Trade, START, END)),
    )

    assert stored_trades == trades
    assert stored_spans == [(START, trades[-1].time + 1)]


@pytest.mark.parametrize(
    "start,end,historical_trades,future_trades,expected_spans",
    [
        # Gap in the middle.
        [
            1,
            5,
            [
                Trade(time=1, price=Decimal("2.0"), size=Decimal("2.0")),
                Trade(time=4, price=Decimal("3.0"), size=Decimal("3.0")),
            ],
            [],
            [(1, 5)],
        ],
        # Full gap (no trades).
        [2, 4, [], [], [(2, 4)]],
        # Historical + future trades.
        [
            0,
            7,
            [
                Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
                Trade(time=1, price=Decimal("2.0"), size=Decimal("2.0")),
                Trade(time=4, price=Decimal("3.0"), size=Decimal("3.0")),
                Trade(time=5, price=Decimal("4.0"), size=Decimal("4.0")),
            ],
            [
                Trade(time=6, price=Decimal("1.0"), size=Decimal("1.0")),
                # We need to add an extra trade here because the current algorithm takes trades
                # until it has reached a trade where time is >= end time.
                Trade(time=7, price=Decimal("1.0"), size=Decimal("1.0")),
            ],
            [(0, 7)],
        ],
        # Gap at the end.
        [
            0,
            4,
            [
                Trade(time=0, price=Decimal("1.0"), size=Decimal("1.0")),
                Trade(time=1, price=Decimal("2.0"), size=Decimal("2.0")),
            ],
            [],
            [(0, 4)],
        ],
    ],
)
async def test_stream_trades(
    mocker: MockerFixture,
    storage: Storage,
    start: Timestamp,
    end: Timestamp,
    historical_trades: list[Trade],
    future_trades: list[Trade],
    expected_spans: list[tuple[Timestamp, Timestamp]],
) -> None:
    SYMBOL = "eth-btc"
    CURRENT = 6
    STORAGE_BATCH_SIZE = 2
    time = fakes.Time(CURRENT, increment=1)
    exchange = mock_exchange(
        mocker,
        trades=historical_trades,
        stream_trades=future_trades,
    )
    trades = Trades(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE,
    )

    output_trades = await list_async(trades.stream_trades(exchange.name, SYMBOL, start, end))
    shard = Storage.key(exchange.name, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, "trade", start, end)),
        list_async(storage.stream_time_series(shard, "trade", Trade, start, end)),
    )

    # We use `future_trades[:-1]` because the algorithm always takes one trade from an exchange
    # past the span to know where to end. But it's not returned by and hence we discard it here.
    expected_trades = historical_trades + future_trades[:-1]
    assert output_trades == expected_trades
    assert stored_trades == output_trades
    assert stored_spans == expected_spans


async def test_stream_trades_no_duplicates_if_same_trade_from_rest_and_websocket(
    mocker: MockerFixture, storage
) -> None:
    time = fakes.Time(1)
    exchange = mock_exchange(
        mocker,
        trades=[Trade(time=0)],
        stream_trades=[Trade(time=0), Trade(time=1), Trade(time=2)],
    )
    trades = Trades(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    count = 0
    async for trade in trades.stream_trades(exchange.name, "eth-btc", 0, 2):
        time.time = trade.time + 1
        count += 1
    assert count == 2
