import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

import pytest

from juno import (
    Depth, ExchangeInfo, Fees, Fill, OrderException, OrderResult, OrderStatus, OrderUpdate
)
from juno.brokers import Limit
from juno.components import Informant, Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, MinNotional, Price, Size
from juno.storages import Memory
from tests import fakes

filters = Filters(
    price=Price(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1')),
    size=Size(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1'))
)
exchange_info = ExchangeInfo(
    fees={'__all__': Fees(maker=Decimal('0.1'), taker=Decimal('0.1'))},
    filters={'__all__': filters}
)
order_client_id = str(uuid4())


async def test_fill() -> None:
    snapshot = Depth.Snapshot(
        asks=[],
        bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))],
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        place_order_result=OrderResult(time=0, status=OrderStatus.NEW),
        future_orders=[
            OrderUpdate.New(
                client_id=order_client_id,
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('1.0'),
                    size=Decimal('0.5'),
                    quote=Decimal('0.5'),
                    fee=Decimal('0.05'),
                    fee_asset='eth',
                ),
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('1.0'),
                    size=Decimal('0.5'),
                    quote=Decimal('0.5'),
                    fee=Decimal('0.05'),
                    fee_asset='eth',
                ),
            ),
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        ]
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        await broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            quote=Decimal('1.0'),
            test=False,
        )


async def test_insufficient_balance() -> None:
    snapshot = Depth.Snapshot(asks=[], bids=[(Decimal('1.0'), Decimal('1.0'))])
    exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(OrderException):
            await broker.buy(
                exchange='exchange',
                account='spot',
                symbol='eth-btc',
                quote=Decimal('0.1'),
                test=False,
            )


async def test_partial_fill_adjust_fill() -> None:
    snapshot = Depth.Snapshot(
        asks=[(Decimal('5.0'), Decimal('1.0'))],
        bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))],
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        future_orders=[
            OrderUpdate.New(
                client_id=order_client_id,
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('1.0'),
                    size=Decimal('1.0'),
                    quote=Decimal('1.0'),
                    fee=Decimal('0.1'),
                    fee_asset='eth',
                ),
            ),
        ]
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            quote=Decimal('2.0'),
            test=False,
        ))
        await yield_control()
        await exchange.depth_queue.put(
            Depth.Update(bids=[(Decimal('2.0') - filters.price.step, Decimal('1.0'))])
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate.Canceled(
                time=0,
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('2.0'),
                    size=Decimal('0.5'),
                    quote=Decimal('1.0'),
                    fee=Decimal('0.05'),
                    fee_asset='eth',
                ),
            )
        )
        await exchange.orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
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


async def test_multiple_cancels() -> None:
    snapshot = Depth.Snapshot(
        asks=[(Decimal('10.0'), Decimal('1.0'))],
        bids=[(Decimal('1.0') - filters.price.step, Decimal('1.0'))],
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            quote=Decimal('10.0'),
            test=False,
        ))
        await yield_control()  # New order.
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('1.0'),
                    size=Decimal('5.0'),
                    quote=Decimal('5.0'),
                    fee=Decimal('0.5'),
                    fee_asset='eth',
                ),
            )
        )
        await yield_control()
        await exchange.depth_queue.put(
            Depth.Update(bids=[(Decimal('2.0') - filters.price.step, Decimal('1.0'))])
        )
        await yield_control()  # Cancel order.
        await exchange.orders_queue.put(
            OrderUpdate.Canceled(
                time=0,
                client_id=order_client_id,
            )
        )
        await yield_control()  # New order.
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.depth_queue.put(
            Depth.Update(bids=[(Decimal('5.0') - filters.price.step, Decimal('1.0'))])
        )
        await yield_control()  # Cancel order.
        await exchange.orders_queue.put(
            OrderUpdate.Canceled(
                time=0,
                client_id=order_client_id,
            )
        )
        await yield_control()  # New order.
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('5.0'),
                    size=Decimal('1.0'),
                    quote=Decimal('5.0'),
                    fee=Decimal('0.1'),
                    fee_asset='eth',
                ),
            )
        )
        await exchange.orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        )
        result = await asyncio.wait_for(task, timeout=1)
        assert result.status is OrderStatus.FILLED
        assert Fill.total_quote(result.fills) == 10
        assert Fill.total_size(result.fills) == Decimal('6.0')
        assert Fill.total_fee(result.fills) == Decimal('0.6')
        assert len(exchange.place_order_calls) == 3
        assert len(exchange.cancel_order_calls) == 2


async def test_partial_fill_cancel_min_notional() -> None:
    snapshot = Depth.Snapshot(
        bids=[(Decimal('99.0'), Decimal('1.0'))],
    )
    exchange_info = ExchangeInfo(
        fees={'__all__': Fees()},
        filters={'__all__': Filters(
            min_notional=MinNotional(min_notional=Decimal('10.0')),
            price=Price(step=Decimal('1.0')),
            size=Size(step=Decimal('0.01')),
        )}
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            quote=Decimal('100.0'),
            test=False,
        ))
        await yield_control()  # New order.
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('100.0'),
                    size=Decimal('0.9'),
                    quote=Decimal('90.0'),
                    fee=Decimal('0.0'),
                    fee_asset='eth',
                ),
            )
        )
        await yield_control()
        await exchange.depth_queue.put(
            Depth.Update(bids=[(Decimal('100.0'), Decimal('1.0'))])
        )
        await yield_control()  # Cancel order.
        await exchange.orders_queue.put(
            OrderUpdate.Canceled(
                time=0,
                client_id=order_client_id,
            )
        )
        await yield_control()
        result = await asyncio.wait_for(task, timeout=1)

        assert result.status is OrderStatus.FILLED
        assert Fill.total_size(result.fills) == Decimal('0.9')
        assert Fill.total_quote(result.fills) == Decimal('90.0')
        assert len(exchange.place_order_calls) == 1
        assert len(exchange.cancel_order_calls) == 1


async def test_buy_places_at_highest_bid_if_no_spread() -> None:
    # Min step is 0.1.
    snapshot = Depth.Snapshot(
        asks=[(Decimal('1.0'), Decimal('1.0'))],
        bids=[(Decimal('0.9'), Decimal('1.0'))],
    )
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            quote=Decimal('0.9'),
            test=False,
        ))
        await yield_control()  # New order.
        await exchange.orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.depth_queue.put(
            Depth.Update(bids=[(Decimal('0.9'), Decimal('2.0'))])
        )
        await yield_control()  # Shouldn't cancel previous order because no spread.
        await exchange.orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal('0.9'),
                    size=Decimal('1.0'),
                    quote=Decimal('0.9'),
                    fee=Decimal('0.1'),
                    fee_asset='eth',
                ),
            )
        )
        await exchange.orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        )
        result = await asyncio.wait_for(task, timeout=1)

        assert result.status is OrderStatus.FILLED
        assert len(exchange.place_order_calls) == 1
        assert len(exchange.cancel_order_calls) == 0
        assert exchange.place_order_calls[0]['price'] == Decimal('0.9')


@asynccontextmanager
async def init_broker(exchange: Exchange) -> AsyncIterator[Limit]:
    memory = Memory()
    informant = Informant(memory, [exchange])
    orderbook = Orderbook([exchange])
    user = User([exchange])
    async with memory, informant, orderbook, user:
        broker = Limit(informant, orderbook, user, get_client_id=lambda: order_client_id)
        yield broker


async def yield_control():
    for _ in range(0, 10):
        await asyncio.sleep(0)