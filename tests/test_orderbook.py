import asyncio
from decimal import Decimal

import pytest

from juno import Depth, ExchangeException, Filters
from juno.asyncio import stream_queue
from juno.components import Orderbook
from juno.filters import Price, Size

from . import fakes

FEE_RATE = Decimal('0.1')
FILTERS = Filters(
    price=Price(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1')),
    size=Size(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1'))
)


async def test_list_asks_bids(storage) -> None:
    snapshot = Depth.Snapshot(
        asks=[
            (Decimal('1.0'), Decimal('1.0')),
            (Decimal('3.0'), Decimal('1.0')),
            (Decimal('2.0'), Decimal('1.0')),
        ],
        bids=[
            (Decimal('1.0'), Decimal('1.0')),
            (Decimal('3.0'), Decimal('1.0')),
            (Decimal('2.0'), Decimal('1.0')),
        ]
    )
    exchange = fakes.Exchange(depth=snapshot)
    exchange.can_stream_depth_snapshot = False

    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('exchange', 'eth-btc') as book:
            asks = book.list_asks()
            bids = book.list_bids()

    assert asks == [
        (Decimal('1.0'), Decimal('1.0')),
        (Decimal('2.0'), Decimal('1.0')),
        (Decimal('3.0'), Decimal('1.0')),
    ]
    assert bids == [
        (Decimal('3.0'), Decimal('1.0')),
        (Decimal('2.0'), Decimal('1.0')),
        (Decimal('1.0'), Decimal('1.0')),
    ]


@pytest.mark.parametrize(
    'size,snapshot_asks,expected_output', [
        (
            Decimal('1.0'),
            [(Decimal('2.0'), Decimal('1.0')), (Decimal('3.0'), Decimal('1.0'))],
            [(Decimal('2.0'), Decimal('1.0'), Decimal('0.1'))],
        ),
        (
            Decimal('3.1'),
            [(Decimal('1.0'), Decimal('2.0')), (Decimal('2.0'), Decimal('2.0'))],
            [
                (Decimal('1.0'), Decimal('2.0'), Decimal('0.2')),
                (Decimal('2.0'), Decimal('1.1'), Decimal('0.11')),
            ],
        ),
    ]
)
async def test_find_order_asks(size, snapshot_asks, expected_output) -> None:
    snapshot = Depth.Snapshot(asks=snapshot_asks, bids=[])
    exchange = fakes.Exchange(depth=snapshot)
    exchange.can_stream_depth_snapshot = False
    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('exchange', 'eth-btc') as book:
            output = book.find_order_asks(size=size, fee_rate=FEE_RATE, filters=FILTERS)
    assert_fills(output, expected_output)


@pytest.mark.parametrize(
    'quote,snapshot_asks,update_asks,expected_output', [
        (
            Decimal('10.0'),
            [(Decimal('1.0'), Decimal('1.0'))],
            [(Decimal('1.0'), Decimal('0.0'))],
            [],
        ),
        (
            Decimal('10.0'),
            [(Decimal('1.0'), Decimal('1.0')), (Decimal('2.0'), Decimal('1.0'))],
            [(Decimal('1.0'), Decimal('1.0'))],
            [
                (Decimal('1.0'), Decimal('1.0'), Decimal('0.1')),
                (Decimal('2.0'), Decimal('1.0'), Decimal('0.1')),
            ],
        ),
        (
            Decimal('11.0'),
            [(Decimal('1.0'), Decimal('11.0'))],
            [],
            [(Decimal('1.0'), Decimal('10.0'), Decimal('1.0'))],
        ),
        (
            Decimal('1.23'),
            [(Decimal('1.0'), Decimal('2.0'))],
            [],
            [(Decimal('1.0'), Decimal('1.2'), Decimal('0.12'))],
        ),
        (
            Decimal('1.0'),
            [(Decimal('2.0'), Decimal('1.0'))],
            [],
            [],
        ),
        (
            Decimal('3.1'),
            [(Decimal('1.0'), Decimal('1.0')), (Decimal('2.0'), Decimal('1.0'))],
            [],
            [
                (Decimal('1.0'), Decimal('1.0'), Decimal('0.1')),
                (Decimal('2.0'), Decimal('1.0'), Decimal('0.1')),
            ],
        ),
    ]
)
async def test_find_order_asks_by_quote(
    quote, snapshot_asks, update_asks, expected_output
) -> None:
    snapshot = Depth.Snapshot(asks=snapshot_asks, bids=[])
    updates = [Depth.Update(asks=update_asks, bids=[])]
    exchange = fakes.Exchange(depth=snapshot, future_depths=updates)
    exchange.can_stream_depth_snapshot = False
    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('exchange', 'eth-btc') as book:
            output = book.find_order_asks(quote=quote, fee_rate=FEE_RATE, filters=FILTERS)
    assert_fills(output, expected_output)


@pytest.mark.parametrize(
    'size,snapshot_bids,update_bids,expected_output',
    [
        (
            Decimal('10.0'),
            [(Decimal('1.0'), Decimal('1.0'))],
            [(Decimal('1.0'), Decimal('0.0'))],
            [],
        ),
        (
            Decimal('10.0'),
            [(Decimal('1.0'), Decimal('1.0')), (Decimal('2.0'), Decimal('1.0'))],
            [(Decimal('1.0'), Decimal('1.0'))],
            [
                (Decimal('2.0'), Decimal('1.0'), Decimal('0.2')),
                (Decimal('1.0'), Decimal('1.0'), Decimal('0.1')),
            ],
        ),
        (
            Decimal('11.0'),
            [(Decimal('1.0'), Decimal('11.0'))],
            [],
            [(Decimal('1.0'), Decimal('10.0'), Decimal('1.0'))],
        ),
        (
            Decimal('1.23'),
            [(Decimal('1.0'), Decimal('2.0'))],
            [],
            [(Decimal('1.0'), Decimal('1.2'), Decimal('0.12'))],
        ),
        (
            Decimal('1.0'),
            [(Decimal('2.0'), Decimal('1.0'))],
            [],
            [(Decimal('2.0'), Decimal('1.0'), Decimal('0.2'))],
        ),
        (
            Decimal('3.1'),
            [(Decimal('1.0'), Decimal('1.0')), (Decimal('2.0'), Decimal('1.0'))],
            [],
            [
                (Decimal('2.0'), Decimal('1.0'), Decimal('0.2')),
                (Decimal('1.0'), Decimal('1.0'), Decimal('0.1')),
            ],
        ),
    ],
)
async def test_find_order_bids(size, snapshot_bids, update_bids, expected_output) -> None:
    snapshot = Depth.Snapshot(asks=[], bids=snapshot_bids)
    updates = [Depth.Update(asks=[], bids=update_bids)]
    exchange = fakes.Exchange(depth=snapshot, future_depths=updates)
    exchange.can_stream_depth_snapshot = False
    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('exchange', 'eth-btc') as book:
            output = book.find_order_bids(size=size, fee_rate=FEE_RATE, filters=FILTERS)
    assert_fills(output, expected_output)


async def test_concurrent_sync_should_not_ping_exchange_multiple_times(mocker) -> None:
    asks = [(Decimal('1.0'), Decimal('1.0'))]

    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.can_stream_depth_snapshot = False
    exchange.get_depth.return_value = Depth.Snapshot(asks=asks)

    async with Orderbook(exchanges=[exchange]) as orderbook:
        # First calls to exchange.
        async with orderbook.sync('magicmock', 'eth-btc') as book1:
            async with orderbook.sync('magicmock', 'eth-btc') as book2:
                assert book2.list_asks() == asks
            assert book1.list_asks() == asks

        # Second calls to exchange.
        async with orderbook.sync('magicmock', 'eth-btc') as book:
            assert book.list_asks() == asks

    assert exchange.get_depth.call_count == 2
    assert exchange.connect_stream_depth.call_count == 2


async def test_concurrent_sync_should_have_isolated_events(mocker) -> None:
    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.can_stream_depth_snapshot = False
    exchange.get_depth.return_value = Depth.Snapshot()
    depths: asyncio.Queue[Depth.Update] = asyncio.Queue()
    exchange.connect_stream_depth.return_value.__aenter__.return_value = stream_queue(depths)

    async with Orderbook(exchanges=[exchange]) as orderbook:
        ctx1 = orderbook.sync('magicmock', 'eth-btc')
        ctx2 = orderbook.sync('magicmock', 'eth-btc')
        book1, book2 = await asyncio.gather(ctx1.__aenter__(), ctx2.__aenter__())

        assert not book1.updated.is_set()
        assert not book2.updated.is_set()

        await depths.put(Depth.Update(asks=[(Decimal('1.0'), Decimal('1.0'))]))
        await depths.join()

        assert book1.updated.is_set()
        assert book2.updated.is_set()

        await book1.updated.wait()
        assert book2.updated.is_set()

        await asyncio.gather(
            ctx1.__aexit__(None, None, None),
            ctx2.__aexit__(None, None, None),
        )


async def test_sync_on_exchange_exception() -> None:
    exchange = fakes.Exchange(
        depth=Depth.Snapshot(asks=[(Decimal('1.0'), Decimal('1.0'))]),
        future_depths=[
            ExchangeException(),
            Depth.Update(asks=[(Decimal('2.0'), Decimal('1.0'))]),
        ],
    )
    exchange.can_stream_depth_snapshot = False
    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('exchange', 'eth-btc') as book:
            await exchange.depth_queue.join()
            assert book.list_asks()


async def test_initial_depth_update_out_of_sync_retry_only_get_depth(mocker) -> None:
    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.can_stream_depth_snapshot = False
    exchange.get_depth.side_effect = [Depth.Snapshot(last_id=1), Depth.Snapshot(last_id=2)]
    depths: asyncio.Queue[Depth.Update] = asyncio.Queue()
    depths.put_nowait(Depth.Update(asks=[(Decimal('1.0'), Decimal('1.0'))], first_id=3, last_id=3))
    exchange.connect_stream_depth.return_value.__aenter__.return_value = stream_queue(depths)

    async with Orderbook(exchanges=[exchange]) as orderbook:
        async with orderbook.sync('magicmock', 'eth-btc') as book:
            await asyncio.wait_for(depths.join(), timeout=1.0)
            assert book.list_asks() == [(Decimal('1.0'), Decimal('1.0'))]


def assert_fills(output, expected_output) -> None:
    for o, (eoprice, eosize, eofee) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
        assert o.fee == eofee
