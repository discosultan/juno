import pytest

import juno
from juno.exchanges import Binance, Coinbase, GateIO, Kraken

from . import fakes
from .exchanges import try_init_exchange


@pytest.fixture(scope='session')
def config():
    return juno.config.from_env()


@pytest.fixture
async def storage(loop):
    async with fakes.Storage() as storage:
        yield storage


@pytest.fixture(scope='session')
async def binance(loop, config):
    async with try_init_exchange(Binance, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def coinbase(loop, config):
    async with try_init_exchange(Coinbase, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def gateio(loop, config):
    async with try_init_exchange(GateIO, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def kraken(loop, config):
    async with try_init_exchange(Kraken, config) as exchange:
        yield exchange
