import pytest

from juno import Candle
from juno.components import Informant
from juno.storages import Memory
from juno.utils import list_async


class Fake:

    candles = [
        (Candle(0, 1.0, 1.0, 1.0, 1.0, 1.0), True),
        (Candle(1, 1.0, 1.0, 1.0, 1.0, 1.0), True),
        # Deliberately skipped candle.
        (Candle(3, 1.0, 1.0, 1.0, 1.0, 1.0), True)
    ]

    async def stream_candles(self, _symbol, _interval, start, end):
        for c, p in ((c, p) for c, p in self.candles if c.time >= start and c.time < end):
            yield c, p


@pytest.fixture
def exchange():
    return Fake()


@pytest.fixture
def memory():
    return Memory()


@pytest.fixture
async def informant(exchange, memory):
    services = {
        'fake': exchange,
        'memory': memory
    }
    config = {
        'exchanges': ['fake'],
        'storage': 'memory'
    }
    async with Informant(services=services, config=config) as informant:
        yield informant


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
