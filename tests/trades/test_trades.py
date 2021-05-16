import asyncio
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from juno.asyncio import cancel, create_queue, list_async, resolved_stream, stream_queue
from juno.storages import Storage
from juno.trades import Trade, Trades
from juno.trades.exchanges import Exchange
from juno.utils import key
from tests import fakes

EXCHANGE = 'magicmock'
SYMBOL = 'eth-btc'


def create_service(
    storage: Storage,
    time: fakes.Time,
    historical_trades: list[Trade] = [],
    future_trades: asyncio.Queue = asyncio.Queue(),
    storage_batch_size: int = 1000,
) -> Trades:
    exchange = MagicMock(spec=Exchange)
    exchange.stream_historical_trades.return_value = resolved_stream(*historical_trades)
    exchange.connect_stream_trades.return_value.__aenter__.return_value = stream_queue(
        future_trades
    )
    return Trades(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        storage_batch_size=storage_batch_size,
    )


async def test_stream_future_trades_span_stored_until_stopped(storage: Storage) -> None:
    start = 0
    end = 10
    trades = [Trade(time=1)]
    future_trades = create_queue(trades)
    time = fakes.Time(start, increment=1)
    service = create_service(
        storage=storage,
        time=time,
        future_trades=future_trades,
    )

    task = asyncio.create_task(
        list_async(service.stream_trades(EXCHANGE, SYMBOL, start, end))
    )
    await future_trades.join()
    time.time = 5
    await cancel(task)

    shard = key(EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'trade', start, end)),
        list_async(storage.stream_time_series(shard, 'trade', Trade, start, end)),
    )
    assert stored_trades == trades
    assert stored_spans == [(start, trades[-1].time + 1)]


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
    time = fakes.Time(6, increment=1)
    service = create_service(
        storage=storage,
        time=time,
        storage_batch_size=2,
        historical_trades=[t for t in historical_trades if t.time >= start and t.time < end],
        future_trades=create_queue(future_trades),
    )

    output_trades = await list_async(service.stream_trades(EXCHANGE, SYMBOL, start, end))
    shard = key(EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(shard, 'trade', start, end)),
        list_async(storage.stream_time_series(shard, 'trade', Trade, start, end)),
    )

    assert output_trades == expected_trades
    assert stored_trades == output_trades
    assert stored_spans == espans


async def test_stream_trades_no_duplicates_if_same_trade_from_rest_and_websocket(
    storage: Storage
) -> None:
    time = fakes.Time(1)
    service = create_service(
        storage=storage,
        time=time,
        historical_trades=[Trade(time=0)],
        future_trades=create_queue([Trade(time=0), Trade(time=1), Trade(time=2)]),
    )

    count = 0
    async for trade in service.stream_trades(EXCHANGE, SYMBOL, 0, 2):
        time.time = trade.time + 1
        count += 1
    assert count == 2
