from contextlib import asynccontextmanager
from typing import Type

import pytest
from pytest_lazyfixture import lazy_fixture

from juno import exchanges
from juno.config import init_instance
from juno.exchanges import Exchange
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


@asynccontextmanager
async def try_init_exchange_session(type_, config):
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
