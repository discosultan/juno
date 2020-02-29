from decimal import Decimal

from juno import DepthSnapshot
from juno.components import Orderbook

from . import fakes


async def test_list_asks_bids(storage) -> None:
    snapshot = DepthSnapshot(
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
