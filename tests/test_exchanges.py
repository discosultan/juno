from datetime import datetime

import aiohttp
import pytest

from juno import config
from juno.exchanges import map_exchanges
from juno.time import datetime_timestamp_ms, HOUR_MS


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
exchanges = map_exchanges(config.load_from_env())
exchange_names = list(exchanges.keys())
exchange_instances = list(exchanges.values())


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchange_instances, ids=exchange_names, indirect=True)
async def test_stream_candles(loop, request, exchange):
    skip_non_manual(request)
    start = datetime_timestamp_ms(datetime(2018, 1, 1))
    stream = exchange.stream_candles(
        symbol='eth-btc',
        interval=HOUR_MS,
        start=start,
        end=start + HOUR_MS)
    await stream.__anext__()
    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchange_instances, ids=exchange_names, indirect=True)
async def test_map_symbol_infos(loop, request, exchange):
    skip_non_manual(request)
    res = await exchange.map_symbol_infos()
    assert len(res) > 0


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchange_instances, ids=exchange_names, indirect=True)
async def test_stream_balances(loop, request, exchange):
    skip_non_manual(request)
    stream = exchange.stream_balances()
    await stream.__anext__()


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchange_instances, ids=exchange_names, indirect=True)
async def test_stream_depth(loop, request, exchange):
    skip_non_manual(request)
    stream = exchange.stream_depth('eth-btc')
    res = await stream.__anext__()
    assert res


def skip_non_manual(request):
    if request.config.option.markexpr != 'manual':
        pytest.skip("Specify 'manual' marker to run! These are run manually as they integrate "
                    "with external exchanges.")
