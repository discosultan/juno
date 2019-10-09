from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

import pytest

from juno import (
    DepthSnapshot, DepthUpdate, Fees, Fill, Fills, InsufficientBalance, OrderResult, OrderStatus,
    OrderUpdate, SymbolInfo
)
from juno.brokers import Limit, Market
from juno.components import Informant, Orderbook
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes

filters = Filters(
    price=Price(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')),
    size=Size(min=Decimal(1), max=Decimal(10), step=Decimal('0.1'))
)
symbol_info = SymbolInfo(
    fees={'__all__': Fees(maker=Decimal('0.1'), taker=Decimal('0.1'))},
    filters={'__all__': filters}
)
order_client_id = str(uuid4())


@pytest.mark.parametrize(
    'quote,snapshot_asks,update_asks,expected_output', [
        (
            Decimal(10),
            [(Decimal(1), Decimal(1))],
            [(Decimal(1), Decimal(0))],
            [],
        ),
        (
            Decimal(10),
            [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
            [(Decimal(1), Decimal(1))],
            [(Decimal(1), Decimal(1), Decimal('0.1')), (Decimal(2), Decimal(1), Decimal('0.1'))],
        ),
        (
            Decimal(11),
            [(Decimal(1), Decimal(11))],
            [],
            [(Decimal(1), Decimal(10), Decimal(1))],
        ),
        (
            Decimal('1.23'),
            [(Decimal(1), Decimal(2))],
            [],
            [(Decimal(1), Decimal('1.2'), Decimal('0.12'))],
        ),
        (
            Decimal(1),
            [(Decimal(2), Decimal(1))],
            [],
            [],
        ),
        (
            Decimal('3.1'),
            [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
            [],
            [(Decimal(1), Decimal(1), Decimal('0.1')), (Decimal(2), Decimal(1), Decimal('0.1'))],
        ),
    ]
)
async def test_market_find_order_asks(quote, snapshot_asks, update_asks, expected_output):
    snapshot = DepthSnapshot(asks=snapshot_asks, bids=[])
    updates = [DepthUpdate(asks=update_asks, bids=[])]
    async with init_market_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=updates,
            symbol_info=symbol_info
        )
    ) as broker:
        output = broker.find_order_asks(exchange='exchange', symbol='eth-btc', quote=quote)
        assert_fills(output, expected_output)


@pytest.mark.parametrize(
    'base,snapshot_bids,update_bids,expected_output',
    [
        (
            Decimal(10),
            [(Decimal(1), Decimal(1))],
            [(Decimal(1), Decimal(0))],
            [],
        ),
        (
            Decimal(10),
            [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
            [(Decimal(1), Decimal(1))],
            [(Decimal(2), Decimal(1), Decimal('0.2')), (Decimal(1), Decimal(1), Decimal('0.1'))],
        ),
        (
            Decimal(11),
            [(Decimal(1), Decimal(11))],
            [],
            [(Decimal(1), Decimal(10), Decimal(1))],
        ),
        (
            Decimal('1.23'),
            [(Decimal(1), Decimal(2))],
            [],
            [(Decimal(1), Decimal('1.2'), Decimal('0.12'))],
        ),
        (
            Decimal(1),
            [(Decimal(2), Decimal(1))],
            [],
            [(Decimal(2), Decimal(1), Decimal('0.2'))],
        ),
        (
            Decimal('3.1'),
            [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
            [],
            [(Decimal(2), Decimal(1), Decimal('0.2')), (Decimal(1), Decimal(1), Decimal('0.1'))],
        ),
    ],
)
async def test_market_find_order_bids(base, snapshot_bids, update_bids, expected_output):
    snapshot = DepthSnapshot(asks=[], bids=snapshot_bids)
    updates = [DepthUpdate(asks=[], bids=update_bids)]
    async with init_market_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=updates,
            symbol_info=symbol_info
        )
    ) as broker:
        output = broker.find_order_bids(exchange='exchange', symbol='eth-btc', base=base)
        assert_fills(output, expected_output)


async def test_market_insufficient_balance():
    snapshot = DepthSnapshot(asks=[(Decimal(1), Decimal(1))], bids=[])
    async with init_market_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=[],
            symbol_info=symbol_info
        )
    ) as broker:
        # Should raise because size filter min is 1.
        with pytest.raises(InsufficientBalance):
            await broker.buy('exchange', 'eth-btc', Decimal('0.5'), True)


async def test_limit_fill_immediately():
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal(1) - filters.price.step, Decimal(1))])
    async with init_limit_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=[],
            symbol_info=symbol_info,
            place_order_result=OrderResult(status=OrderStatus.FILLED, fills=Fills(
                Fill(price=Decimal(1), size=Decimal(1), fee=Decimal(0), fee_asset='eth')
            ))
        )
    ) as broker:
        await broker.buy('exchange', 'eth-btc', Decimal(1), False)


async def test_limit_fill_partially():
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal(1) - filters.price.step, Decimal(1))])
    async with init_limit_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=[],
            symbol_info=symbol_info,
            place_order_result=OrderResult(status=OrderStatus.NEW, fills=Fills()),
            orders=[
                OrderUpdate(
                    symbol='eth-btc',
                    status=OrderStatus.PARTIALLY_FILLED,
                    client_id=order_client_id,
                    price=Decimal(1),
                    size=Decimal('0.5'),
                    # cumulative_filled_size=Decimal(0),
                    fee=Decimal(0),
                    fee_asset='eth'
                ),
                OrderUpdate(
                    symbol='eth-btc',
                    status=OrderStatus.FILLED,
                    client_id=order_client_id,
                    price=Decimal(1),
                    size=Decimal('0.5'),
                    # cumulative_filled_size=Decimal(0),
                    fee=Decimal(0),
                    fee_asset='eth'
                ),
            ]
        )
    ) as broker:
        await broker.buy('exchange', 'eth-btc', Decimal(1), False)


async def test_limit_insufficient_balance():
    snapshot = DepthSnapshot(asks=[], bids=[(Decimal(1), Decimal(1))])
    async with init_limit_broker(
        fakes.Exchange(
            depth_snapshot=snapshot,
            depth_updates=[],
            symbol_info=symbol_info
        )
    ) as broker:
        # Should raise because size filter min is 1.
        with pytest.raises(InsufficientBalance):
            await broker.buy('exchange', 'eth-btc', Decimal('0.5'), False)


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
