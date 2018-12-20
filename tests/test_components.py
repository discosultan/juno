import pytest

from juno import Balance, Candle, SymbolInfo
from juno.components import Informant, Wallet
from juno.storages import Memory
from juno.utils import list_async


class Fake:

    candles = [
        (Candle(0, 1.0, 1.0, 1.0, 1.0, 1.0), True),
        (Candle(1, 1.0, 1.0, 1.0, 1.0, 1.0), True),
        # Deliberately skipped candle.
        (Candle(3, 1.0, 1.0, 1.0, 1.0, 1.0), True)
    ]

    async def map_symbol_infos(self):
        return {'eth-btc': SymbolInfo(
            min_size=1.0,
            max_size=1.0,
            size_step=1.0,
            min_price=1.0,
            max_price=1.0,
            price_step=1.0)
        }

    async def map_balances(self):
        return {'btc': Balance(
            available=1.0,
            hold=0.0)
        }

    async def stream_candles(self, _symbol, _interval, start, end):
        for c, p in ((c, p) for c, p in self.candles if c.time >= start and c.time < end):
            yield c, p


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
        'storage': 'memory'
    }


@pytest.fixture
async def informant(services, config):
    async with Informant(services=services, config=config) as informant:
        yield informant


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
