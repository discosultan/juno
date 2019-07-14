from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

import aiohttp
import pytest

from juno import OrderType, Side
from juno.config import load_instance
from juno.exchanges import Binance, Coinbase
from juno.time import HOUR_MS, UTC, datetime_timestamp_ms

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


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_fees(loop, request, exchange):
    skip_non_configured(request, exchange)
    res = await exchange.map_fees()
    assert res


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_filters(loop, request, exchange):
    skip_non_configured(request, exchange)
    res = await exchange.map_filters()
    assert len(res) > 0


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_balances(loop, request, exchange):
    skip_non_configured(request, exchange)
    async with exchange.connect_stream_balances() as stream:
        await stream.__anext__()


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_candles(loop, request, exchange):
    skip_non_configured(request, exchange)
    start = datetime_timestamp_ms(datetime(2018, 1, 1, tzinfo=UTC))
    async with exchange.connect_stream_candles(
        symbol='eth-btc', interval=HOUR_MS, start=start, end=start + HOUR_MS
    ) as stream:
        candle = await stream.__anext__()

    assert isinstance(candle.time, int)
    assert isinstance(candle.close, Decimal)

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_depth(loop, request, exchange):
    skip_non_configured(request, exchange)
    async with exchange.connect_stream_depth('eth-btc') as stream:
        assert await stream.__anext__()


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_place_order(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Coinbase)
    await exchange.place_order(
        symbol='eth-btc', side=Side.BID, type_=OrderType.MARKET, size=Decimal(1), test=True
    )


def skip_non_configured(request, exchange):
    markers = ['exchange', 'manual']
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    if not exchange:
        pytest.skip("Exchange params not configured")


def skip_exchange(exchange, *skip_exchange_types):
    type_ = type(exchange)
    if type_ in skip_exchange_types:
        pytest.skip(f'not implemented for {type_.__name__.lower()}')


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with load_instance(type_, config) as exchange:
            yield exchange
    except TypeError:
        yield None
