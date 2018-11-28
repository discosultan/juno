import os

import pytest

from juno.exchanges import Binance, Coinbase
from juno.time import time_ms


# We use a session-scoped loop for shared rate-limiting.
@pytest.fixture(scope='session')
def loop():
    with aiohttp.test_utils.loop_context() as loop:
        yield loop


@pytest.fixture(scope='session')
async def exchange(request):
    async with request.param:
        yield request.param


# We only test exchanges for which all envs are setup.
exchanges = []
for exchange_type in [Binance, Coinbase]:
    name = exchange_type.__name__.upper()
    keys = exchange_type.__init__.__annotations__.keys()  # type: ignore
    kwargs = {key: os.getenv(f'JUNO_{name}_{key.upper()}') for key in keys}
    if all(kwargs.values()):
        exchanges.append(exchange_type(**kwargs))

# Used for pretty parametrized tests output.
exchange_names = [exchange.__class__.__name__ for exchange in exchanges]


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_names,
                         indirect=True)
async def test_get_filled_orders(exchange):
    if request.config.option.markexpr != 'manual':
        pytest.skip("Specify 'manual' marker to run! These are run manually "
                    "as they integrate with external exchanges")

    h1_ago = time_ms() - 1000 * 60 * 1
    # await exchange.get_filled_orders(limit=1, since=h1_ago)
