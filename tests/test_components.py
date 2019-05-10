from contextlib import asynccontextmanager
from decimal import Decimal
from functools import partial

import pytest

from juno import Balance, Candle, Fees
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
from juno.storages import Memory
from juno.utils import list_async


async def test_stream_candles(loop):
    candles = [
        (Candle(0, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True),
        (Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True),
        # Deliberately skipped candle.
        (Candle(3, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True)
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


async def test_get_fees(loop):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    async with init_informant(Fake(fees={'__all__': fees})) as informant:
        out_fees = informant.get_fees('fake', 'eth-btc')
        assert out_fees == fees
    async with init_informant(Fake(fees={'eth-btc': fees})) as informant:
        out_fees = informant.get_fees('fake', 'eth-btc')
        assert out_fees == fees


async def test_get_filters(loop):
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(1), step=Decimal(1)),
        size=Size(min=Decimal(1), max=Decimal(1), step=Decimal(1)))
    async with init_informant(Fake(filters={'eth-btc': filters})) as informant:
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
    depths = [{
        'type': 'snapshot',
        'asks': snapshot_asks,
        'bids': [],
    }, {
        'type': 'update',
        'asks': update_asks,
        'bids': [],
    }]
    async with init_orderbook(Fake(depths=depths)) as orderbook:
        filters = Filters(
            price=Price(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')),
            size=Size(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')))
        output = orderbook.find_market_order_asks(exchange='fake', symbol='eth-btc', quote=quote,
                                                  fees=Fees.none(), filters=filters)
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
    depths = [{
        'type': 'snapshot',
        'asks': [],
        'bids': snapshot_bids,
    }, {
        'type': 'update',
        'asks': [],
        'bids': update_bids,
    }]
    async with init_orderbook(Fake(depths=depths)) as orderbook:
        filters = Filters(
            price=Price(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')),
            size=Size(min=Decimal(1), max=Decimal(10), step=Decimal('0.1')))
        output = orderbook.find_market_order_bids(exchange='fake', symbol='eth-btc', base=base,
                                                  fees=Fees.none(), filters=filters)
        _assert_fills(output, expected_output)


async def test_list_asks_bids(loop):
    depths = [{
        'type': 'snapshot',
        'asks': [(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
        'bids': [(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
    }]
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
    def __init__(self, candles=[], fees={}, filters={}, balances={}, depths={}, orders=[]):
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

    async def stream_balances(self):
        for balance in self.balances:
            yield balance

    async def stream_candles(self, symbol, interval, start, end):
        for c, p in ((c, p) for c, p in self.candles if c.time >= start and c.time < end):
            yield c, p

    async def stream_depth(self, symbol):
        for depth in self.depths:
            yield depth

    async def stream_orders(self):
        for order in self.orders:
            yield order

    async def place_order(self, *args, **kwargs):
        pass

    async def cancel_order(self, *args, **kwargs):
        pass


@asynccontextmanager
async def init_component(type_, exchange):
    async with Memory() as memory:
        services = {
            'fake': exchange,
            'memory': memory
        }
        config = {
            'storage': 'memory',
            'agents': [
                {'symbol': 'eth-btc'}
            ]
        }
        async with type_(services=services, config=config) as component:
            yield component


init_informant = partial(init_component, Informant)
init_orderbook = partial(init_component, Orderbook)
init_wallet = partial(init_component, Wallet)


def _assert_fills(output, expected_output):
    for o, (eoprice, eosize) in zip(output, expected_output):
        assert o.price == eoprice
        assert o.size == eosize
