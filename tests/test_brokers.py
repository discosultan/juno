from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

from juno import DepthUpdate, DepthUpdateType
from juno.brokers import Market
from juno.components import Informant, Orderbook
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes


@pytest.mark.parametrize('quote,snapshot_asks,update_asks,expected_output', [
    (Decimal(10), [(Decimal(1), Decimal(1))], [(Decimal(1), Decimal(0))], []),
    (Decimal(10),
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
     [(Decimal(1), Decimal(1))],
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))]),
    (Decimal(11), [(Decimal(1), Decimal(11))], [], [(Decimal(1), Decimal(10))]),
    (Decimal('1.23'), [(Decimal(1), Decimal(2))], [], [(Decimal(1), Decimal('1.2'))]),
    (Decimal(1), [(Decimal(2), Decimal(1))], [], []),
    (Decimal('3.1'),
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
     [],
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))]),
])
async def test_find_order_asks(loop, quote, snapshot_asks, update_asks, expected_output):
    depths = [
        DepthUpdate(
            type=DepthUpdateType.SNAPSHOT,
            asks=snapshot_asks,
            bids=[]),
        DepthUpdate(
            type=DepthUpdateType.UPDATE,
            asks=update_asks,
            bids=[])
    ]
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')),
        size=Size(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')))
    async with init_market_broker(fakes.Exchange(depths=depths, filters={'__all__': filters})
                                  ) as broker:
        output = broker.find_order_asks(exchange='exchange', symbol='eth-btc', quote=quote)
        assert_fills(output, expected_output)


@pytest.mark.parametrize('base,snapshot_bids,update_bids,expected_output', [
    (Decimal(10), [(Decimal(1), Decimal(1))], [(Decimal(1), Decimal(0))], []),
    (Decimal(10),
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
     [(Decimal(1), Decimal(1))],
     [(Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]),
    (Decimal(11), [(Decimal(1), Decimal(11))], [], [(Decimal(1), Decimal(10))]),
    (Decimal('1.23'), [(Decimal(1), Decimal(2))], [], [(Decimal(1), Decimal('1.2'))]),
    (Decimal(1), [(Decimal(2), Decimal(1))], [], [(Decimal(2), Decimal(1))]),
    (Decimal('3.1'),
     [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
     [],
     [(Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]),
])
async def test_find_order_bids(loop, base, snapshot_bids, update_bids, expected_output):
    depths = [
        DepthUpdate(
            type=DepthUpdateType.SNAPSHOT,
            asks=[],
            bids=snapshot_bids),
        DepthUpdate(
            type=DepthUpdateType.UPDATE,
            asks=[],
            bids=update_bids)
    ]
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')),
        size=Size(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')))
    async with init_market_broker(fakes.Exchange(depths=depths, filters={'__all__': filters})
                                  ) as broker:
        output = broker.find_order_bids(exchange='exchange', symbol='eth-btc', base=base)
        assert_fills(output, expected_output)


@asynccontextmanager
async def init_market_broker(*exchanges):
    memory = Memory()
    informant = Informant(memory, exchanges)
    orderbook = Orderbook(exchanges, config={'symbol': 'eth-btc'})
    async with memory, informant, orderbook:
        broker = Market(informant, orderbook, exchanges)
        yield broker


def assert_fills(output, expected_output):
    for o, (eoprice, eosize) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
