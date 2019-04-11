from contextlib import asynccontextmanager
from datetime import datetime

import aiohttp
import pytest

from juno.exchanges import Binance, Coinbase, create_exchange
from juno.time import HOUR_MS, datetime_timestamp_ms

exchange_types = [Binance, Coinbase]
exchanges = [pytest.lazy_fixture(e.__name__.lower()) for e in exchange_types]
exchange_ids = [e.__name__ for e in exchange_types]


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


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_candles(loop, request, exchange):
    skip_non_configured(request, exchange)
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
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_symbol_infos(loop, request, exchange):
    skip_non_configured(request, exchange)
    res = await exchange.map_symbol_infos()
    assert len(res) > 0


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_balances(loop, request, exchange):
    skip_non_configured(request, exchange)
    stream = exchange.stream_balances()
    await stream.__anext__()


@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_depth(loop, request, exchange):
    skip_non_configured(request, exchange)
    stream = exchange.stream_depth('eth-btc')
    res = await stream.__anext__()
    assert res


def skip_non_configured(request, exchange):
    if request.config.option.markexpr != 'manual':
        pytest.skip("Specify 'manual' marker to run! These are run manually as they integrate "
                    "with external exchanges")
    if not exchange:
        pytest.skip("Exchange params not configured")


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with create_exchange(type_, config) as exchange:
            yield exchange
    except ValueError:
        yield None
