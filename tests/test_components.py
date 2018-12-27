from decimal import Decimal

import pytest

from juno import Balance, Candle, SymbolInfo
from juno.components import Informant, Orderbook, Wallet
from juno.storages import Memory
from juno.utils import list_async


class Fake:

    candles = [
        (Candle(0, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True),
        (Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True),
        # Deliberately skipped candle.
        (Candle(3, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1)), True)
    ]

    async def map_symbol_infos(self):
        return {'eth-btc': SymbolInfo(
            min_size=Decimal(1),
            max_size=Decimal(1),
            size_step=Decimal(1),
            min_price=Decimal(1),
            max_price=Decimal(1),
            price_step=Decimal(1))
        }

    async def stream_balances(self):
        yield {'btc': Balance(
            available=Decimal(1),
            hold=Decimal(0)
        )}

    async def stream_candles(self, _symbol, _interval, start, end):
        for c, p in ((c, p) for c, p in self.candles if c.time >= start and c.time < end):
            yield c, p

    async def stream_depth(self, _symbol):
        yield {
            'type': 'snapshot',
            'bids': [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1))],
            'asks': [(Decimal(1), Decimal(1))]
        }
        yield {
            'type': 'update',
            'bids': [(Decimal(1), Decimal(1))],
            'asks': [(Decimal(1), Decimal(0))]
        }


@pytest.fixture
def exchange():
    return Fake()


@pytest.fixture
async def memory():
    async with Memory() as storage:
        yield storage


@pytest.fixture
def services(exchange, memory):
    return {
        'fake': exchange,
        'memory': memory
    }


@pytest.fixture
def config():
    return {
        'exchanges': ['fake'],
        'storage': 'memory',
        'symbols': ['eth-btc']
    }


@pytest.fixture
async def informant(services, config):
    async with Informant(services=services, config=config) as informant:
        yield informant


@pytest.fixture
async def orderbook(services, config):
    async with Orderbook(services=services, config=config) as orderbook:
        yield orderbook


@pytest.fixture
async def wallet(services, config):
    async with Wallet(services=services, config=config) as wallet:
        yield wallet


async def test_stream_candles(loop, informant, exchange):
    # -> 0
    # -> 1
    # -> 2 missing
    candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 0, 3))
    assert candles == exchange.candles[:2]

    # -> 2 missing
    candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 2, 3))
    assert candles == []

    # -> 2 missing
    # -> 3
    candles = await list_async(informant.stream_candles('fake', 'eth-btc', 1, 3, 4))
    assert candles == exchange.candles[-1:]


async def test_get_symbol_info(loop, informant):
    symbol_info = informant.get_symbol_info('fake', 'eth-btc')
    assert symbol_info


async def test_get_balance(loop, wallet):
    balance = wallet.get_balance('fake', 'btc')
    assert balance


async def test_find_market_order_buy_size(loop, orderbook):
    size = orderbook.find_market_order_buy_size(
        exchange='fake',
        symbol='eth-btc',
        quote_balance=Decimal('0.5'),
        size_step=Decimal('0.1'))
    assert size == 0


async def test_find_market_order_sell_size(loop, orderbook):
    size = orderbook.find_market_order_sell_size(
        exchange='fake',
        symbol='eth-btc',
        base_balance=Decimal('2.5'),
        size_step=Decimal('0.1'))
    assert size == 2
