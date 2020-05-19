from decimal import Decimal

import pytest

from juno import Depth, Filters
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

    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        asks = orderbook.list_asks(exchange='exchange', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='exchange', symbol='eth-btc')

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
    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        output = orderbook.find_order_asks(
            exchange='exchange', symbol='eth-btc', size=size, fee_rate=FEE_RATE, filters=FILTERS
        )
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
    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        output = orderbook.find_order_asks_by_quote(
            exchange='exchange', symbol='eth-btc', quote=quote, fee_rate=FEE_RATE, filters=FILTERS
        )
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
    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        output = orderbook.find_order_bids(
            exchange='exchange', symbol='eth-btc', size=size, fee_rate=FEE_RATE, filters=FILTERS
        )
        assert_fills(output, expected_output)


async def test_sync_on_demand() -> None:
    exchange = fakes.Exchange(depth=Depth.Snapshot(asks=[(Decimal('1.0'), Decimal('1.0'))]))
    exchange.can_stream_depth_snapshot = False
    async with Orderbook(exchanges=[exchange]) as orderbook:
        assert orderbook.list_asks('exchange', 'eth-btc') == []

        await orderbook.ensure_sync(['exchange'], ['eth-btc'])
        # Second call shouldn't do anything.
        await orderbook.ensure_sync(['exchange'], ['eth-btc'])
        assert orderbook.list_asks('exchange', 'eth-btc') == [(Decimal('1.0'), Decimal('1.0'))]


def assert_fills(output, expected_output) -> None:
    for o, (eoprice, eosize, eofee) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
        assert o.fee == eofee
