import aiohttp.test_utils
import pytest

import juno
from juno.exchanges import Binance, Coinbase, GateIO, Kraken

from . import fakes
from .exchanges import try_init_exchange_session


@pytest.fixture(scope='session')
def loop():
    with aiohttp.test_utils.loop_context() as loop:
        yield loop


@pytest.fixture(scope='session')
def config():
    return juno.config.from_env()


@pytest.fixture(scope='session')
async def binance(loop, config):
    async with try_init_exchange_session(Binance, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def coinbase(loop, config):
    async with try_init_exchange_session(Coinbase, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def gateio(loop, config):
    async with try_init_exchange_session(GateIO, config) as exchange:
        yield exchange


@pytest.fixture(scope='session')
async def kraken(loop, config):
    async with try_init_exchange_session(Kraken, config) as exchange:
        yield exchange


@pytest.fixture
async def storage(loop):
    async with fakes.Storage() as storage:
        yield storage
