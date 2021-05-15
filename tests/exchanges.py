from contextlib import asynccontextmanager
from typing import Type

import aiohttp
import pytest
from pytest_lazyfixture import lazy_fixture

from juno import exchanges
from juno.config import init_instance
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken
from juno.utils import list_concretes_from_module

exchange_type_fixtures = {
    e: lazy_fixture(e.__name__.lower()) for e in list_concretes_from_module(exchanges, Exchange)
}


def parametrize_exchange(exchange_types: list[Type[Exchange]]):
    return pytest.mark.parametrize(
        'exchange_session',
        [exchange_type_fixtures[e] for e in exchange_types],
        ids=[e.__name__ for e in exchange_types],
    )


# We use a session-scoped loop for shared rate-limiting.
@pytest.fixture(scope='session')
def loop():
    with aiohttp.test_utils.loop_context() as loop:
        yield loop


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


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with init_instance(type_, config) as exchange:
            yield exchange
    except TypeError:
        yield None


def skip_not_configured(request, exchange):
    markers = ['exchange', 'manual']
    if request.config.option.markexpr not in markers:
        pytest.skip(f'Specify {"" or "".join(markers)} marker to run!')
    if not exchange:
        pytest.skip('Exchange params not configured')
