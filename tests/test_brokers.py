import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

import pytest

from juno import (
    DepthSnapshot, DepthUpdate, ExchangeInfo, Fees, Fill, OrderException, OrderResult, OrderStatus,
    OrderUpdate
)
from juno.brokers import Limit, Market
from juno.components import Informant, Orderbook
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes

filters = Filters(
    price=Price(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1')),
    size=Size(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1'))
)
exchange_info = ExchangeInfo(
    fees={'__all__': Fees(maker=Decimal('0.1'), taker=Decimal('0.1'))},
    filters={'__all__': filters}
)
order_client_id = str(uuid4())


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
async def test_market_find_order_asks(size, snapshot_asks, expected_output) -> None:
    snapshot = DepthSnapshot(asks=snapshot_asks, bids=[])
    exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_market_broker(exchange) as broker:
        output = broker.find_order_asks(exchange='exchange', symbol='eth-btc', size=size)
        assert_fills(output, expected_output)


# async def test_market_find_order_asks_invalid_size() -> None:
#     snapshot = DepthSnapshot(asks=[], bids=[])
#     exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
#     exchange.can_stream_depth_snapshot = False
#     invalid_size = Decimal('0.12')
#     async with init_market_broker(exchange) as broker:
#         with pytest.raises(OrderException):
#             broker.find_order_asks(exchange='exchange', symbol='eth-btc', size=invalid_size)


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
async def test_market_find_order_asks_by_quote(
    quote, snapshot_asks, update_asks, expected_output
) -> None:
    snapshot = DepthSnapshot(asks=snapshot_asks, bids=[])
    updates = [DepthUpdate(asks=update_asks, bids=[])]
    exchange = fakes.Exchange(depth=snapshot, future_depths=updates, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_market_broker(exchange) as broker:
        output = broker.find_order_asks_by_quote(
            exchange='exchange', symbol='eth-btc', quote=quote
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
async def test_market_find_order_bids(size, snapshot_bids, update_bids, expected_output) -> None:
    snapshot = DepthSnapshot(asks=[], bids=snapshot_bids)
    updates = [DepthUpdate(asks=[], bids=update_bids)]
    exchange = fakes.Exchange(depth=snapshot, future_depths=updates, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_market_broker(exchange) as broker:
        output = broker.find_order_bids(exchange='exchange', symbol='eth-btc', size=size)
        assert_fills(output, expected_output)


async def test_market_insufficient_balance() -> None:
    snapshot = DepthSnapshot(asks=[(Decimal('1.0'), Decimal('1.0'))], bids=[])
    exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_market_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(OrderException):
            await broker.buy_by_quote(
                exchange='exchange',
                symbol='eth-btc',
                quote=Decimal('0.1'),
                test=True,
            )


async def test_limit_fill_immediately() -> None:
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))])
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        future_orders=[
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.FILLED,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('1.0'),
                filled_size=Decimal('1.0'),
                cumulative_filled_size=Decimal('1.0'),
                fee=Decimal('0.1'),
                fee_asset='eth',
            )
        ]
    )
    exchange.can_stream_depth_snapshot = False
    async with init_limit_broker(exchange) as broker:
        await broker.buy_by_quote(
            exchange='exchange',
            symbol='eth-btc',
            quote=Decimal('1.0'),
            test=False,
        )


async def test_limit_fill_partially() -> None:
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))])
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        place_order_result=OrderResult(status=OrderStatus.NEW, fills=[]),
        future_orders=[
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.PARTIALLY_FILLED,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('1.0'),
                filled_size=Decimal('0.5'),
                cumulative_filled_size=Decimal('0.5'),
                fee=Decimal('0.05'),
                fee_asset='eth',
            ),
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.FILLED,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('1.0'),
                filled_size=Decimal('0.5'),
                cumulative_filled_size=Decimal('1.0'),
                fee=Decimal('0.05'),
                fee_asset='eth',
            ),
        ]
    )
    exchange.can_stream_depth_snapshot = False
    async with init_limit_broker(exchange) as broker:
        await broker.buy_by_quote(
            exchange='exchange',
            symbol='eth-btc',
            quote=Decimal('1.0'),
            test=False,
        )


async def test_limit_insufficient_balance() -> None:
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal('1.0'), Decimal('1.0'))])
    exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_limit_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(OrderException):
            await broker.buy_by_quote(
                exchange='exchange',
                symbol='eth-btc',
                quote=Decimal('0.1'),
                test=False,
            )


async def test_limit_partial_fill_adjust_fill() -> None:
    snapshot = DepthSnapshot(
        asks=[(Decimal('5.0'), Decimal('1.0'))],
        bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))],
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        future_orders=[
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.NEW,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('2.0'),
            ),
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.PARTIALLY_FILLED,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('2.0'),
                filled_size=Decimal('1.0'),
                filled_quote=Decimal('1.0'),
                cumulative_filled_size=Decimal('1.0'),
                fee=Decimal('0.1'),
                fee_asset='eth',
            ),
        ]
    )
    exchange.can_stream_depth_snapshot = False
    async with init_limit_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy_by_quote(
            exchange='exchange',
            symbol='eth-btc',
            quote=Decimal('2.0'),
            test=False,
        ))
        await yield_control()
        await exchange.depth_queue.put(
            DepthUpdate(bids=[(Decimal('2.0') - filters.price.step, Decimal('1.0'))])
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.CANCELED,
                client_id=order_client_id,
                price=Decimal('1.0'),
                size=Decimal('2.0'),
                cumulative_filled_size=Decimal('1.0'),
            )
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.NEW,
                client_id=order_client_id,
                price=Decimal('2.0'),
                size=Decimal('0.5'),
            )
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate(
                symbol='eth-btc',
                status=OrderStatus.FILLED,
                client_id=order_client_id,
                price=Decimal('2.0'),
                size=Decimal('0.5'),
                filled_size=Decimal('0.5'),
                filled_quote=Decimal('1.0'),
                cumulative_filled_size=Decimal('0.5'),
                fee=Decimal('0.05'),
                fee_asset='eth',
            )
        )
        result = await asyncio.wait_for(task, timeout=1)
        assert result.status is OrderStatus.FILLED
        assert Fill.total_quote(result.fills) == 2
        assert Fill.total_size(result.fills) == Decimal('1.5')
        assert Fill.total_fee(result.fills) == Decimal('0.15')
        assert len(exchange.place_order_calls) == 2
        assert exchange.place_order_calls[0]['price'] == 1
        assert exchange.place_order_calls[0]['size'] == 2
        assert exchange.place_order_calls[1]['price'] == 2
        assert exchange.place_order_calls[1]['size'] == Decimal('0.5')
        assert len(exchange.cancel_order_calls) == 1


@asynccontextmanager
async def init_market_broker(*exchanges):
    memory = Memory()
    informant = Informant(memory, exchanges)
    orderbook = Orderbook(exchanges, config={'symbol': 'eth-btc'})
    async with memory, informant, orderbook:
        broker = Market(informant, orderbook, exchanges)
        yield broker


@asynccontextmanager
async def init_limit_broker(*exchanges):
    memory = Memory()
    informant = Informant(memory, exchanges)
    orderbook = Orderbook(exchanges, config={'symbol': 'eth-btc'})
    async with memory, informant, orderbook:
        broker = Limit(informant, orderbook, exchanges, get_client_id=lambda: order_client_id)
        yield broker


def assert_fills(output, expected_output):
    for o, (eoprice, eosize, eofee) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
        assert o.fee == eofee


async def yield_control():
    for _ in range(0, 10):
        await asyncio.sleep(0)
