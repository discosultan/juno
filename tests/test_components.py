from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

from juno import Balance, DepthUpdate, DepthUpdateType, Fees
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
from juno.storages import Memory
from juno.utils import list_async

from .utils import new_candle


async def test_stream_candles(loop):
    candles = [
        new_candle(time=0),
        new_candle(time=1),
        # Deliberately skipped candle.
        new_candle(time=3)
    ]
    async with init_informant(Fake(candles=candles)) as informant:
        # -> 0
        # -> 1
        # -> 2 missing
        out_candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 0, 3))
        assert out_candles == candles[:2]

        # -> 2 missing
        out_candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 2, 3))
        assert out_candles == []

        # -> 2 missing
        # -> 3
        out_candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 3, 4))
        assert out_candles == candles[-1:]


@pytest.mark.parametrize('exchange_fees_key', ['__all__', 'eth-btc'])
async def test_get_fees(loop, exchange_fees_key):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    async with init_informant(Fake(fees={exchange_fees_key: fees})) as informant:
        out_fees = informant.get_fees('fake', 'eth-btc')
        assert out_fees == fees


@pytest.mark.parametrize('exchange_filters_key', ['__all__', 'eth-btc'])
async def test_get_filters(loop, exchange_filters_key):
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(1), step=Decimal(1)),
        size=Size(min=Decimal(1), max=Decimal(1), step=Decimal(1)))
    async with init_informant(Fake(filters={exchange_filters_key: filters})) as informant:
        out_filters = informant.get_filters('fake', 'eth-btc')
        assert out_filters == filters


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
async def test_find_market_order_asks(loop, quote, snapshot_asks, update_asks, expected_output):
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
    async with init_orderbook(Fake(depths=depths, filters={'__all__': filters})) as orderbook:
        output = orderbook.find_market_order_asks(exchange='fake', symbol='eth-btc', quote=quote)
        _assert_fills(output, expected_output)


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
async def test_find_market_order_bids(loop, base, snapshot_bids, update_bids, expected_output):
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
    async with init_orderbook(Fake(depths=depths, filters={'__all__': filters})) as orderbook:
        output = orderbook.find_market_order_bids(exchange='fake', symbol='eth-btc', base=base)
        _assert_fills(output, expected_output)


async def test_list_asks_bids(loop):
    depths = [
        DepthUpdate(
            type=DepthUpdateType.SNAPSHOT,
            asks=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
            bids=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))])
    ]
    async with init_orderbook(Fake(depths=depths)) as orderbook:
        asks = orderbook.list_asks(exchange='fake', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='fake', symbol='eth-btc')

    assert asks == [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(3), Decimal(1))]
    assert bids == [(Decimal(3), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]


async def test_get_balance(loop):
    balance = Balance(available=Decimal(1), hold=Decimal(0))
    async with init_wallet(Fake(balances=[{'btc': balance}])) as wallet:
        out_balance = wallet.get_balance('fake', 'btc')
        assert out_balance == balance


class Fake(Exchange):
    def __init__(self, candles=[], fees={'__all__': Fees.none()},
                 filters={'__all__': Filters.none()}, balances=[], depths=[], orders=[]):
        self.candles = candles
        self.fees = fees
        self.filters = filters
        self.balances = balances
        self.depths = depths
        self.orders = orders

    async def map_fees(self):
        return self.fees

    async def map_filters(self):
        return self.filters

    @asynccontextmanager
    async def stream_balances(self):
        async def inner():
            for balance in self.balances:
                yield balance
        yield inner()

    @asynccontextmanager
    async def stream_candles(self, symbol, interval, start, end):
        async def inner():
            for c in (c for c in self.candles if c.time >= start and c.time < end):
                yield c
        yield inner()

    @asynccontextmanager
    async def stream_depth(self, symbol):
        async def inner():
            for depth in self.depths:
                yield depth
        yield inner()

    @asynccontextmanager
    async def stream_orders(self):
        async def inner():
            for order in self.orders:
                yield order
        yield inner()

    async def place_order(self, *args, **kwargs):
        pass

    async def cancel_order(self, *args, **kwargs):
        pass


@asynccontextmanager
async def init_informant(exchange):
    async with Memory() as memory:
        async with Informant(storage=memory, exchanges=[exchange]) as component:
            yield component


@asynccontextmanager
async def init_orderbook(exchange):
    async with Memory() as memory:
        async with Informant(storage=memory, exchanges=[exchange]) as informant:
            async with Orderbook(informant=informant, exchanges=[exchange],
                                 config={'symbol': 'eth-btc'}) as component:
                yield component


@asynccontextmanager
async def init_wallet(exchange):
    async with Wallet(exchanges=[exchange]) as component:
        yield component


def _assert_fills(output, expected_output):
    for o, (eoprice, eosize) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
