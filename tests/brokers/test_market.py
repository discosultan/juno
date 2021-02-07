import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

import pytest

from juno import BadOrder, Depth, ExchangeInfo, Fees, Fill, OrderResult, OrderStatus
from juno.brokers import Market
from juno.components import Informant, Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
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


async def test_insufficient_balance() -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal('1.0'), Decimal('1.0'))], bids=[])
    exchange = fakes.Exchange(depth=snapshot, exchange_info=exchange_info)
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        # Should raise because size filter min is 0.2.
        with pytest.raises(BadOrder):
            await broker.buy(
                exchange='exchange',
                account='spot',
                symbol='eth-btc',
                quote=Decimal('0.1'),
                test=True,
            )


async def test_buy() -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal('1.0'), Decimal('1.0'))], bids=[])
    order_result = OrderResult(time=0, status=OrderStatus.FILLED, fills=[
        Fill.with_computed_quote(
            price=Decimal('1.0'), size=Decimal('0.2'), fee=Decimal('0.02'), fee_asset='eth'
        ),
    ])
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        place_order_result=order_result,
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        res = await broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            size=Decimal('0.25'),
            test=False,
        )
    assert res == order_result
    assert len(exchange.place_order_calls) == 1
    assert exchange.place_order_calls[0]['size'] == Decimal('0.2')


@asynccontextmanager
async def init_broker(exchange: Exchange) -> AsyncIterator[Market]:
    memory = Memory()
    informant = Informant(memory, [exchange])
    orderbook = Orderbook([exchange])
    user = User([exchange])
    async with memory, informant, orderbook, user:
        broker = Market(informant, orderbook, user)
        yield broker


async def yield_control():
    for _ in range(0, 10):
        await asyncio.sleep(0)
