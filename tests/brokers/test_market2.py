import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

from juno import Depth, ExchangeInfo, Fees, Fill, OrderResult, OrderStatus, OrderUpdate
from juno.brokers import Market2
from juno.components import Informant, Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
from juno.storages import Memory
from tests import fakes

filters = Filters(
    price=Price(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1')),
    size=Size(min=Decimal('0.2'), max=Decimal('10.0'), step=Decimal('0.1')),
)
exchange_info = ExchangeInfo(
    fees={'__all__': Fees(maker=Decimal('0.1'), taker=Decimal('0.1'))},
    filters={'__all__': filters},
)
order_client_id = str(uuid4())


async def test_buy() -> None:
    snapshot = Depth.Snapshot(asks=[(Decimal('1.0'), Decimal('1.0'))], bids=[])
    exchange = fakes.Exchange(
        depth=snapshot,
        exchange_info=exchange_info,
        client_id=order_client_id,
    )
    exchange.can_stream_depth_snapshot = False
    async with init_broker(exchange) as broker:
        task = asyncio.create_task(broker.buy(
            exchange='exchange',
            account='spot',
            symbol='eth-btc',
            size=Decimal('0.25'),
            test=False,
        ))
        exchange.orders_queue.put_nowait(OrderUpdate.New(
            client_id=order_client_id,
        ))
        exchange.orders_queue.put_nowait(OrderUpdate.Match(
            client_id=order_client_id,
            fill=Fill(
                price=Decimal('1.0'),
                size=Decimal('0.2'),
                quote=Decimal('0.2'),
                fee=Decimal('0.02'),
                fee_asset='eth',
            ),
        ))
        exchange.orders_queue.put_nowait(OrderUpdate.Done(
            time=1,
            client_id=order_client_id,
        ))
        res = await task
    assert res == OrderResult(
        time=1,
        status=OrderStatus.FILLED,
        fills=[Fill.with_computed_quote(
            price=Decimal('1.0'), size=Decimal('0.2'), fee=Decimal('0.02'), fee_asset='eth'
        )],
    )
    assert len(exchange.place_order_calls) == 1
    assert exchange.place_order_calls[0]['size'] == Decimal('0.2')


@asynccontextmanager
async def init_broker(exchange: Exchange) -> AsyncIterator[Market2]:
    memory = Memory()
    informant = Informant(memory, [exchange])
    orderbook = Orderbook([exchange])
    user = User([exchange])
    async with memory, informant, orderbook, user:
        broker = Market2(informant, orderbook, user)
        yield broker


async def yield_control():
    for _ in range(0, 10):
        await asyncio.sleep(0)
