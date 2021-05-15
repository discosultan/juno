import asyncio
from decimal import Decimal

import pytest

from juno.asyncio import cancel, list_async
from juno.storages import Storage
from juno.trades import Trade, Trades
from juno.utils import key
from tests import fakes


async def test_stream_future_trades_span_stored_until_stopped(storage: Storage) -> None:
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    START = 0
    CANCEL_AT = 5
    END = 10
    trades = [Trade(time=1)]
    exchange = fakes.Exchange(future_trades=trades)
    time = fakes.Time(START, increment=1)
    trades_component = Trades(
        storage=storage, exchanges=[exchange], get_time_ms=time.get_time
    )

    task = asyncio.create_task(
        list_async(trades_component.stream_trades(EXCHANGE, SYMBOL, START, END))
    )
    await exchange.trade_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    shard = key(EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'trade', START, END)),
        list_async(storage.stream_time_series(shard, 'trade', Trade, START, END)),
    )

    assert stored_trades == trades
    assert stored_spans == [(START, trades[-1].time + 1)]


@pytest.mark.parametrize(
    'start,end,efrom,eto,espans',
    [
        [1, 5, 1, 3, [(1, 5)]],  # Middle trades.
        [2, 4, 0, 0, [(2, 4)]],  # Empty if no trades.
        [0, 7, 0, 5, [(0, 7)]],  # Includes future trade.
        [0, 4, 0, 2, [(0, 4)]],  # Middle trades with cap at the end.
    ]
)
async def test_stream_trades(storage: Storage, start, end, efrom, eto, espans) -> None:
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    CURRENT = 6
    STORAGE_BATCH_SIZE = 2
    historical_trades = [
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('2.0'), size=Decimal('2.0')),
        Trade(time=4, price=Decimal('3.0'), size=Decimal('3.0')),
        Trade(time=5, price=Decimal('4.0'), size=Decimal('4.0')),
    ]
    future_trades = [
        Trade(time=6, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=7, price=Decimal('1.0'), size=Decimal('1.0')),
    ]
    expected_trades = (historical_trades + future_trades)[efrom:eto]
    time = fakes.Time(CURRENT, increment=1)
    exchange = fakes.Exchange(
        historical_trades=historical_trades,
        future_trades=future_trades,
    )
    trades = Trades(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE,
    )

    output_trades = await list_async(trades.stream_trades(EXCHANGE, SYMBOL, start, end))
    shard = key(EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'trade', start, end)),
        list_async(storage.stream_time_series(shard, 'trade', Trade, start, end)),
    )

    assert output_trades == expected_trades
    assert stored_trades == output_trades
    assert stored_spans == espans


async def test_stream_trades_no_duplicates_if_same_trade_from_rest_and_websocket(
    storage
) -> None:
    time = fakes.Time(1)
    exchange = fakes.Exchange(
        historical_trades=[Trade(time=0)],
        future_trades=[Trade(time=0), Trade(time=1), Trade(time=2)],
    )
    trades = Trades(storage=storage, exchanges=[exchange], get_time_ms=time.get_time)

    count = 0
    async for trade in trades.stream_trades('exchange', 'eth-btc', 0, 2):
        time.time = trade.time + 1
        count += 1
    assert count == 2
