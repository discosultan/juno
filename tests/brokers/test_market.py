import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from juno import BadOrder, Depth, ExchangeInfo, Fees, Fill, OrderResult, OrderStatus, OrderUpdate
from juno.brokers import Market
from juno.components import Informant, Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
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


async def test_insufficient_balance(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal("1.0"), Decimal("1.0"))], bids=[])
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        can_stream_depth_snapshot=False,
    )
    async with init_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(BadOrder):
            await broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                quote=Decimal("0.1"),
                test=True,
            )


async def test_buy(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal("1.0"), Decimal("1.0"))], bids=[])
    order_result = OrderResult(
        time=0,
        status=OrderStatus.FILLED,
        fills=[
            Fill.with_computed_quote(
                price=Decimal("1.0"), size=Decimal("0.2"), fee=Decimal("0.02"), fee_asset="eth"
            ),
        ],
    )
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        place_order_result=order_result,
        can_stream_depth_snapshot=False,
    )
    async with init_broker(exchange) as broker:
        res = await broker.buy(
            exchange=exchange.name,
            account="spot",
            symbol="eth-btc",
            size=Decimal("0.25"),
            test=False,
        )
    assert res == order_result
    assert exchange.place_order.call_count == 1
    assert exchange.place_order.mock_calls[0].kwargs["size"] == Decimal("0.2")


async def test_buy_with_result_over_websocket(mocker: MockerFixture) -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal("1.0"), Decimal("1.0"))], bids=[])
    exchange = mock_exchange(
        mocker,
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
        can_stream_depth_snapshot=False,
        can_get_market_order_result_direct=False,
    )
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(
            broker.buy(
                exchange=exchange.name,
                account="spot",
                symbol="eth-btc",
                size=Decimal("0.25"),
                test=False,
            )
        )
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.New(
                client_id=order_client_id,
            )
        )
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.Match(
                client_id=order_client_id,
                fill=Fill(
                    price=Decimal("1.0"),
                    size=Decimal("0.2"),
                    quote=Decimal("0.2"),
                    fee=Decimal("0.02"),
                    fee_asset="eth",
                ),
            )
        )
        exchange.stream_orders_queue.put_nowait(
            OrderUpdate.Done(time=1, client_id=order_client_id)
        )
        res = await task
    assert res == OrderResult(
        time=1,
        status=OrderStatus.FILLED,
        fills=[
            Fill.with_computed_quote(
                price=Decimal("1.0"), size=Decimal("0.2"), fee=Decimal("0.02"), fee_asset="eth"
            )
        ],
    )
    assert exchange.place_order.call_count == 1
    assert exchange.place_order.mock_calls[0].kwargs["size"] == Decimal("0.2")


@asynccontextmanager
async def init_broker(exchange: Exchange) -> AsyncIterator[Market]:
    memory = Memory()
    informant = Informant(memory, [exchange])
    orderbook = Orderbook([exchange])
    user = User([exchange])
    async with memory, informant, orderbook, user:
        broker = Market(informant, orderbook, user)
        yield broker
