from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Dict

import aiohttp
import pytest
from pytest_lazyfixture import lazy_fixture

import juno
from juno import Balance, Candle, Depth, ExchangeInfo, Ticker, Trade
from juno.asyncio import resolved_stream, zip_async
from juno.config import init_instance
from juno.exchanges import Binance, Coinbase, Exchange, Kraken
from juno.time import HOUR_MS, MIN_MS, strptimestamp, time_ms
from juno.typing import types_match
from juno.utils import list_concretes_from_module

exchange_types = list_concretes_from_module(juno.exchanges, Exchange)
exchanges = [lazy_fixture(e.__name__.lower()) for e in exchange_types]
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


@pytest.fixture(scope='session')
async def kraken(loop, config):
    async with try_init_exchange(Kraken, config) as exchange:
        yield exchange


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_exchange_info(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    info = await exchange.get_exchange_info()

    assert len(info.fees) > 0
    first_fees = next(iter(info.fees.values()))
    assert 0 <= first_fees.taker <= Decimal('0.1')
    assert 0 <= first_fees.maker <= Decimal('0.1')
    assert -4 <= first_fees.taker.as_tuple().exponent <= -1
    assert -4 <= first_fees.maker.as_tuple().exponent <= -1
    if '__all__' not in info.fees:
        assert info.fees['eth-btc']

    assert len(info.filters) > 0
    if '__all__' not in info.filters:
        assert info.filters['eth-btc']

    assert types_match(info, ExchangeInfo)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_tickers(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_list_all_tickers)

    # Note, this is an expensive call!
    tickers = await exchange.map_tickers()

    assert len(tickers) > 0
    assert types_match(tickers, Dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_one_ticker(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    tickers = await exchange.map_tickers(symbols=['eth-btc'])

    assert len(tickers) == 1
    assert types_match(tickers, Dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_spot_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    balances = await exchange.map_balances(account='spot')
    assert types_match(balances, Dict[str, Dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_cross_margin_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_margin_trade)

    balances = await exchange.map_balances(account='margin')
    assert types_match(balances, Dict[str, Dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_map_isolated_margin_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_margin_trade)

    balances = await exchange.map_balances(account='isolated')
    assert types_match(balances, Dict[str, Dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_max_borrowable(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_margin_trade)

    size = await exchange.get_max_borrowable(account='margin', asset='btc')

    assert types_match(size, Decimal)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_historical_candles(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_stream_historical_candles)

    start = strptimestamp('2018-01-01')

    count = 0
    async for candle in exchange.stream_historical_candles(
        symbol='eth-btc', interval=HOUR_MS, start=start, end=start + HOUR_MS
    ):
        if count == 1:
            pytest.fail('Expected a single candle')
        count += 1

        assert types_match(candle, Candle)
        assert candle.time == start


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_candles(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(exchange.can_stream_candles)

    async with exchange.connect_stream_candles(symbol='eth-btc', interval=MIN_MS) as stream:
        async for candle in stream:
            assert types_match(candle, Candle)
            break


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_get_depth(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)
    skip_no_capability(not exchange.can_stream_depth_snapshot)

    depth = await exchange.get_depth('eth-btc')

    assert types_match(depth, Depth.Snapshot)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_depth(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    expected_types = (
        [Depth.Snapshot, Depth.Update] if exchange.can_stream_depth_snapshot else [Depth.Update]
    )

    async with exchange.connect_stream_depth('eth-btc') as stream:
        async for depth, expected_type in zip_async(stream, resolved_stream(*expected_types)):
            assert types_match(depth, expected_type)


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_stream_historical_trades(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # Coinbase can only stream from most recent, hence we use current time.
    if isinstance(exchange, Coinbase):
        end = time_ms()
        start = end - 5 * MIN_MS
    else:
        start = strptimestamp('2018-01-01')
        end = start + HOUR_MS

    stream = exchange.stream_historical_trades(symbol='eth-btc', start=start, end=end)
    async for trade in stream:
        assert types_match(trade, Trade)
        assert trade.time >= start
        break


@pytest.mark.exchange
@pytest.mark.manual
@pytest.mark.parametrize('exchange', exchanges, ids=exchange_ids)
async def test_connect_stream_trades(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # FIAT pairs seem to be more active where supported.
    symbol = 'eth-btc' if isinstance(exchange, Binance) else 'eth-eur'

    async with exchange.connect_stream_trades(symbol=symbol) as stream:
        async for trade in stream:
            assert types_match(trade, Trade)
            break


def skip_not_configured(request, exchange):
    markers = ['exchange', 'manual']
    if request.config.option.markexpr not in markers:
        pytest.skip(f'Specify {"" or "".join(markers)} marker to run!')
    if not exchange:
        pytest.skip('Exchange params not configured')


def skip_exchange(exchange, *skip_exchange_types):
    type_ = type(exchange)
    if type_ in skip_exchange_types:
        pytest.skip(f'Not implemented for {type_.__name__.lower()}')


def skip_no_capability(has_capability):
    if not has_capability:
        pytest.skip('Does not have the capability')


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with init_instance(type_, config) as exchange:
            yield exchange
    except TypeError:
        yield None
