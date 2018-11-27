import os

import pytest

from juno.exchanges import Binance
from juno.time import time_ms


# We only test exchanges for which API key and secrets are setup.
exchanges = []
for exchange_type in [Binance]:
    name = exchange_type.__name__.upper()
    api_key = os.getenv(f'BP_{name}_API_KEY')
    api_secret = os.getenv(f'BP_{name}_API_SECRET')
    if api_key and api_secret:
        exchanges.append(exchange_type(api_key, api_secret))

# Used for pretty parametrized tests output.
exchange_names = [exchange.__class__.__name__ for exchange in exchanges]


# Note: this needs to be function scoped as pytest-asyncio eventloop is
# function scoped.
@pytest.fixture
async def exchange(request):
    async with request.param:
        yield request.param


@pytest.mark.asyncio
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_names,
                         indirect=True)
async def test_get_filled_orders(exchange):
    h1_ago = time_ms() - 1000 * 60 * 1
    # await exchange.get_filled_orders(limit=1, since=h1_ago)
