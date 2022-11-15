import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from juno import (
    BadOrder,
    CancelledReason,
    Depth,
    ExchangeInfo,
    Fees,
    Fill,
    InsufficientFunds,
    OrderResult,
    OrderStatus,
    OrderUpdate,
)
from juno.brokers import Limit
from juno.components import Informant, Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, MinNotional, Price, Size
from juno.storages import Memory
from tests.mocks import mock_exchange

filters = Filters(
    price=Price(min=Decimal("0.2"), max=Decimal("10.0"), step=Decimal("0.1")),
    size=Size(min=Decimal("0.2"), max=Decimal("10.0"), step=Decimal("0.1")),
)
exchange_info = ExchangeInfo(
    fees={"__all__": Fees(maker=Decimal("0.1"), taker=Decimal("0.1"))},
    filters={"__all__": filters},
)
order_client_id = str(uuid4())


async def test_fill(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[],
        bids=[(Decimal("1.0") - filters.price.step, Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        exchange_info=exchange_info,
        depth=snapshot,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )

    def place_order(*args, **kwargs):
        for order in [
            OrderUpdate.New(
                client_id=order_client_id,
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("0.5"),
                    quote=Decimal("0.5"),
                    fee=Decimal("0.05"),
                    fee_asset="eth",
                ),
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("0.5"),
                    quote=Decimal("0.5"),
                    fee=Decimal("0.05"),
                    fee_asset="eth",
                ),
            ),
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            ),
        ]:
            exchange.stream_orders_queue.put_nowait(order)
        return OrderResult(time=0, status=OrderStatus.NEW)

    exchange.place_order.side_effect = place_order

    async with init_broker(exchange) as broker:
        await broker.buy(
            exchange=exchange.name,
            account="spot",
            symbol="eth-btc",
            quote=Decimal("1.0"),
            test=False,
        )


async def test_insufficient_balance(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(asks=[], bids=[(Decimal("1.0"), Decimal("1.0"))])
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )
    async with init_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(BadOrder):
            await broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("0.1"),
                test=False,
            )


async def test_partial_fill_adjust_fill(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[(Decimal("5.0"), Decimal("1.0"))],
        bids=[(Decimal("1.0") - filters.price.step, Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )

    def place_order(*args, **kwargs):
        for order in [
            OrderUpdate.New(
                client_id=order_client_id,
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("1.0"),
                    quote=Decimal("1.0"),
                    fee=Decimal("0.1"),
                    fee_asset="eth",
                ),
            ),
        ]:
            exchange.stream_orders_queue.put_nowait(order)
        return OrderResult(time=0, status=OrderStatus.NEW)

    exchange.place_order.side_effect = place_order

    async with init_broker(exchange) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("2.0"),
                test=False,
            )
        )
        await yield_control()
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("2.0") - filters.price.step, Decimal("1.0"))])
        )
        await yield_control()
        await exchange.stream_orders_queue.put(
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            )
        )
        await yield_control()
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.stream_orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("2.0"),
                    size=Decimal("0.5"),
                    quote=Decimal("1.0"),
                    fee=Decimal("0.05"),
                    fee_asset="eth",
                ),
            )
        )
        await exchange.stream_orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        )
        result = await asyncio.wait_for(task, timeout=1)
        assert result.status is OrderStatus.FILLED
        assert Fill.total_quote(result.fills) == 2
        assert Fill.total_size(result.fills) == Decimal("1.5")
        assert Fill.total_fee(result.fills, "eth") == Decimal("0.15")
        assert exchange.place_order.call_count == 2
        assert exchange.place_order.mock_calls[0].kwargs["price"] == 1
        assert exchange.place_order.mock_calls[0].kwargs["size"] == 2
        assert exchange.place_order.mock_calls[1].kwargs["price"] == 2
        assert exchange.place_order.mock_calls[1].kwargs["size"] == Decimal("0.5")
        assert exchange.cancel_order.call_count == 1


async def test_multiple_cancels(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[(Decimal("10.0"), Decimal("1.0"))],
        bids=[(Decimal("1.0") - filters.price.step, Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("10.0"),
                test=False,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.stream_orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("5.0"),
                    quote=Decimal("5.0"),
                    fee=Decimal("0.5"),
                    fee_asset="eth",
                ),
            )
        )
        await yield_control()
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("2.0") - filters.price.step, Decimal("1.0"))])
        )
        await yield_control()  # Cancel order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("5.0") - filters.price.step, Decimal("1.0"))])
        )
        await yield_control()  # Cancel order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await yield_control()
        await exchange.stream_orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("5.0"),
                    size=Decimal("1.0"),
                    quote=Decimal("5.0"),
                    fee=Decimal("0.1"),
                    fee_asset="eth",
                ),
            )
        )
        await exchange.stream_orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        )
        result = await asyncio.wait_for(task, timeout=1)
        assert result.status is OrderStatus.FILLED
        assert Fill.total_quote(result.fills) == 10
        assert Fill.total_size(result.fills) == Decimal("6.0")
        assert Fill.total_fee(result.fills, "eth") == Decimal("0.6")
        assert exchange.place_order.call_count == 3
        assert exchange.cancel_order.call_count == 2


async def test_partial_fill_cancel_min_notional(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        bids=[(Decimal("99.0"), Decimal("1.0"))],
    )
    exchange_info = ExchangeInfo(
        fees={"__all__": Fees()},
        filters={
            "__all__": Filters(
                min_notional=MinNotional(min_notional=Decimal("10.0")),
                price=Price(step=Decimal("1.0")),
                size=Size(step=Decimal("0.01")),
            )
        },
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("100.0"),
                test=False,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("100.0"), Decimal("1.0"))])
        )
        await yield_control()
        await exchange.stream_orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("100.0"),
                    size=Decimal("0.9"),
                    quote=Decimal("90.0"),
                    fee=Decimal("0.0"),
                    fee_asset="eth",
                ),
            )
        )
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("100.0"), Decimal("0.1"))])
        )
        await yield_control()
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("100.0"), Decimal("1.0"))])
        )
        await yield_control()  # Cancel order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            )
        )
        await yield_control()
        result = await asyncio.wait_for(task, timeout=1)

        assert result.status is OrderStatus.FILLED
        assert Fill.total_size(result.fills) == Decimal("0.9")
        assert Fill.total_quote(result.fills) == Decimal("90.0")
        assert exchange.place_order.call_count == 1
        assert exchange.cancel_order.call_count == 1


async def test_buy_places_at_highest_bid_if_no_spread(mocker: MockerFixture) -> None:
    # Min step is 0.1.
    snapshot = Depth.Snapshot(
        asks=[(Decimal("1.0"), Decimal("1.0"))],
        bids=[(Decimal("0.9"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("0.9"),
                test=False,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("0.9"), Decimal("2.0"))])
        )
        await yield_control()  # Shouldn't cancel previous order because no spread.
        await exchange.stream_orders_queue.put(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("0.9"),
                    size=Decimal("1.0"),
                    quote=Decimal("0.9"),
                    fee=Decimal("0.1"),
                    fee_asset="eth",
                ),
            )
        )
        await exchange.stream_orders_queue.put(
            OrderUpdate.Done(
                time=0,
                client_id=order_client_id,
            )
        )
        result = await asyncio.wait_for(task, timeout=1)

        assert result.status is OrderStatus.FILLED
        assert exchange.place_order.call_count == 1
        assert exchange.cancel_order.call_count == 0
        assert exchange.place_order.mock_calls[0].kwargs["price"] == Decimal("0.9")


async def test_cancels_open_order_on_error(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[(Decimal("2.0"), Decimal("1.0"))],
        bids=[(Decimal("1.0"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )

    def place_order(*args, **kwargs):
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        return OrderResult(time=0, status=OrderStatus.NEW)

    exchange.place_order.side_effect = place_order

    async with init_broker(exchange, cancel_order_on_error=True) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("1.0"),
                test=False,
            )
        )
        await yield_control()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert exchange.place_order.call_count == 1
        assert exchange.place_order.mock_calls[0].kwargs["client_id"] == order_client_id
        assert exchange.cancel_order.call_count == 1
        assert exchange.cancel_order.mock_calls[0].kwargs["client_id"] == order_client_id


async def test_buy_does_not_place_higher_bid_if_highest_only_self(mocker: MockerFixture) -> None:
    # Min step is 0.1.
    snapshot = Depth.Snapshot(
        asks=[(Decimal("2.0"), Decimal("1.0"))],
        bids=[(Decimal("1.0"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )
    async with init_broker(exchange, cancel_order_on_error=False) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("1.1"),
                test=False,
            )
        )
        await yield_control()  # New order.
        await exchange.stream_orders_queue.put(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        await exchange.stream_depth_queue.put(
            Depth.Update(bids=[(Decimal("1.1"), Decimal("1.0"))])
        )
        await yield_control()  # Shouldn't cancel previous order because only ours' is highest.

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert exchange.place_order.call_count == 1
        assert exchange.place_order.mock_calls[0].kwargs["price"] == Decimal("1.1")
        assert exchange.cancel_order.call_count == 0


async def test_buy_matching_order_placement_strategy(mocker: MockerFixture) -> None:
    # Min step is 0.1.
    # Fee is 10%.
    snapshot = Depth.Snapshot(
        asks=[(Decimal("2.0"), Decimal("1.0"))],
        bids=[(Decimal("1.0"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=False,
    )

    def place_order(*args, **kwargs):
        if exchange.place_order.call_count == 1:  # First.
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.New(
                    client_id=order_client_id,
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.0"), Decimal("2.0"))])
            )
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Match(
                    client_id=order_client_id,
                    fill=Fill(
                        price=Decimal("1.0"),
                        size=Decimal("0.5"),
                        quote=Decimal("0.5"),
                        fee=Decimal("0.05"),
                        fee_asset="eth",
                    ),
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.5"), Decimal("1.0"))])
            )
        elif exchange.place_order.call_count == 2:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.New(
                    client_id=order_client_id,
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.5"), Decimal("1.5"))])
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.5"), Decimal("0.3"))])
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("0.5"), Decimal("1.0"))])
            )
        elif exchange.place_order.call_count == 3:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.New(
                    client_id=order_client_id,
                )
            )
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Match(
                    client_id=order_client_id,
                    fill=Fill(
                        price=Decimal("0.5"),
                        size=Decimal("1"),
                        quote=Decimal("0.5"),
                        fee=Decimal("0.1"),
                        fee_asset="eth",
                    ),
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("0.5"), Decimal("1.0"))])
            )
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Done(
                    time=0,
                    client_id=order_client_id,
                )
            )

        return OrderResult(time=0, status=OrderStatus.NEW)

    def cancel_order(*args, **kwargs):
        if exchange.cancel_order.call_count == 1:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Cancelled(
                    time=0,
                    client_id=order_client_id,
                    reason=CancelledReason.UNKNOWN,
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.0"), Decimal("0.0"))])
            )
        elif exchange.cancel_order.call_count == 2:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Cancelled(
                    time=0,
                    client_id=order_client_id,
                    reason=CancelledReason.UNKNOWN,
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("1.5"), Decimal("0.0"))])
            )

    exchange.place_order.side_effect = place_order
    exchange.cancel_order.side_effect = cancel_order

    async with init_broker(exchange, order_placement_strategy="matching") as broker:
        result = await broker.buy(
            exchange=exchange.name,
            account="spot",
            symbol="eth-btc",
            quote=Decimal("1"),
            test=False,
        )

        assert result.status is OrderStatus.FILLED
        assert Fill.total_size(result.fills) == Decimal("1.5")
        assert exchange.place_order.call_count == 3
        assert exchange.cancel_order.call_count == 2


async def test_edit_order(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[],
        bids=[(Decimal("1.0"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        exchange_info=exchange_info,
        depth=snapshot,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=True,
        can_edit_order_atomic=False,
    )

    def place_order(*args, **kwargs):
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        exchange.stream_depth_queue.put_nowait(
            Depth.Update(bids=[(Decimal("2.0"), Decimal("1.0"))])
        )
        return OrderResult(time=0, status=OrderStatus.NEW)

    def edit_order(*args, **kwargs):
        for order_update in [
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            ),
            OrderUpdate.New(
                client_id=order_client_id,
            ),
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("2.0"),
                    size=Decimal("0.5"),
                    quote=Decimal("1.0"),
                    fee=Decimal("0.05"),
                    fee_asset="eth",
                ),
            ),
            OrderUpdate.Done(
                time=1,
                client_id=order_client_id,
            ),
        ]:
            exchange.stream_orders_queue.put_nowait(order_update)
        # TODO: This is completely unnecessary. However, the test hangs without it. We probably
        # don't cleanup async generator somewhere correctly
        exchange.stream_depth_queue.put_nowait(
            Depth.Update(bids=[(Decimal("0.0"), Decimal("0.0"))])
        )

    exchange.place_order.side_effect = place_order
    exchange.edit_order.side_effect = edit_order

    async with init_broker(
        exchange,
        use_edit_order_if_possible=True,
        order_placement_strategy="matching",
    ) as broker:
        result = await broker.buy(
            exchange=exchange.name,
            account="spot",
            symbol="eth-btc",
            quote=Decimal("1"),
            test=False,
        )

        assert result.status is OrderStatus.FILLED
        assert len(result.fills) == 1
        assert result.fills[0].size == Decimal("0.5")
        assert exchange.place_order.call_count == 1
        assert exchange.edit_order.call_count == 1


async def test_edit_order_match_before_order_insufficient_funds(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(
        asks=[],
        bids=[(Decimal("1.0"), Decimal("1.0"))],
    )
    exchange = mock_exchange(
        mocker,
        exchange_info=exchange_info,
        depth=snapshot,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_edit_order=True,
        can_edit_order_atomic=False,
    )

    def place_order(*args, **kwargs):
        if exchange.place_order.call_count == 1:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.New(
                    client_id=order_client_id,
                )
            )
            exchange.stream_depth_queue.put_nowait(
                Depth.Update(bids=[(Decimal("2.0"), Decimal("1.0"))])
            )
            return OrderResult(time=0, status=OrderStatus.NEW)
        elif exchange.place_order.call_count == 2:
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.New(
                    client_id=order_client_id,
                )
            )
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Match(
                    client_id=order_client_id,
                    fill=Fill(
                        price=Decimal("2.0"),
                        size=Decimal("0.25"),
                        quote=Decimal("0.5"),
                        fee=Decimal("0.025"),
                        fee_asset="eth",
                    ),
                )
            )
            exchange.stream_orders_queue.put_nowait(
                OrderUpdate.Done(
                    time=0,
                    client_id=order_client_id,
                )
            )

    def edit_order(*args, **kwargs):
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("0.5"),
                    quote=Decimal("0.5"),
                    fee=Decimal("0.05"),
                    fee_asset="eth",
                ),
            )
        )
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.Cancelled(
                time=0,
                client_id=order_client_id,
                reason=CancelledReason.UNKNOWN,
            )
        )
        # Unable to place the new order because we received a match during order edit.
        raise InsufficientFunds()

    exchange.place_order.side_effect = place_order
    exchange.edit_order.side_effect = edit_order

    async with init_broker(
        exchange,
        use_edit_order_if_possible=True,
        order_placement_strategy="matching",
    ) as broker:
        result = await broker.buy(
            exchange=exchange.name,
            account="spot",
            symbol="eth-btc",
            quote=Decimal("1"),
            test=False,
        )

        assert result.status is OrderStatus.FILLED
        assert len(result.fills) == 2
        assert result.fills[0].size == Decimal("0.5")
        assert result.fills[1].size == Decimal("0.25")
        assert exchange.place_order.call_count == 2
        assert exchange.edit_order.call_count == 1


@asynccontextmanager
async def init_broker(
    exchange: Exchange,
    cancel_order_on_error: bool = True,
    use_edit_order_if_possible: bool = False,
    order_placement_strategy: Limit.OrderPlacementStrategy = "leading",
) -> AsyncIterator[Limit]:
    memory = Memory()
    informant = Informant(memory, [exchange])
    orderbook = Orderbook([exchange])
    user = User([exchange])
    async with memory, informant, orderbook, user:
        broker = Limit(
            informant=informant,
            orderbook=orderbook,
            user=user,
            cancel_order_on_error=cancel_order_on_error,
            use_edit_order_if_possible=use_edit_order_if_possible,
            order_placement_strategy=order_placement_strategy,
        )
        yield broker


async def yield_control():
    for _ in range(0, 10):
        await asyncio.sleep(0)
