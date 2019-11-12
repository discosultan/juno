from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Dict

import aiohttp
import pytest

from juno import Balance, OrderType, Side
from juno.config import load_instance
from juno.exchanges import Binance, Coinbase, Kraken
from juno.time import HOUR_MS, UTC, datetime_timestamp_ms

from .utils import types_match

exchange_types = [
    Binance,
    Coinbase,
    Kraken,
]
exchanges = [pytest.lazy_fixture(e.__name__.lower()) for e in exchange_types]
exchange_ids = [e.__name__ for e in exchange_types]

# TODO: implement missing exchange methods.


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
async def kraken(loop, config):
    async with try_init_exchange(Kraken, config) as exchange:
        yield exchange


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_symbols_info(loop, request, exchange):
    skip_non_configured(request, exchange)

    res = await exchange.get_symbols_info()

    assert len(res.fees) > 0
    assert types_match(next(iter(res.fees.values())))
    if '__all__' not in res.fees:
        assert res.fees['eth-btc']

    assert len(res.filters) > 0
    assert types_match(next(iter(res.filters.values())))
    if '__all__' not in res.filters:
        assert res.filters['eth-btc']

    assert types_match(res)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_balances(loop, request, exchange):
    skip_non_configured(request, exchange)

    res = await exchange.get_balances()

    assert types_match(res, Dict[str, Balance])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_historical_candles(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Kraken)
    start = datetime_timestamp_ms(datetime(2018, 1, 1, tzinfo=UTC))
    stream = exchange.stream_historical_candles(
        symbol='eth-btc', interval=HOUR_MS, start=start, end=start + HOUR_MS
    )
    candle = await stream.__anext__()

    assert types_match(candle)
    assert candle.time == start

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_candles(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Coinbase)

    async with exchange.connect_stream_candles(symbol='eth-btc', interval=HOUR_MS) as stream:
        candle = await stream.__anext__()
        await stream.aclose()

    assert types_match(candle)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_depth(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Coinbase, Kraken)

    res = await exchange.get_depth('eth-btc')

    assert types_match(res)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_depth(loop, request, exchange):
    skip_non_configured(request, exchange)

    async with exchange.connect_stream_depth('eth-btc') as stream:
        res = await stream.__anext__()
        await stream.aclose()

    assert types_match(res)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_place_order(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Coinbase, Kraken)

    await exchange.place_order(
        symbol='eth-btc', side=Side.BUY, type_=OrderType.MARKET, size=Decimal(1), test=True
    )


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_historical_trades(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Coinbase)
    start = datetime_timestamp_ms(datetime(2018, 1, 1, tzinfo=UTC))

    stream = exchange.stream_historical_trades(
        symbol='eth-btc', start=start, end=start + HOUR_MS
    )
    trade = await stream.__anext__()
    await stream.aclose()

    assert types_match(trade)
    assert trade.time >= start


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_trades(loop, request, exchange):
    skip_non_configured(request, exchange)
    skip_exchange(exchange, Binance, Coinbase)
    symbol = 'btc-eur' if isinstance(exchange, Kraken) else 'eth-btc'

    async with exchange.connect_stream_trades(symbol=symbol) as stream:
        trade = await stream.__anext__()
        await stream.aclose()

    assert types_match(trade)


def skip_non_configured(request, exchange):
    markers = ['exchange', 'manual']
    if request.config.option.markexpr not in markers:
        pytest.skip(f'Specify {"" or "".join(markers)} marker to run!')
    if not exchange:
        pytest.skip('Exchange params not configured')


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
