from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Type

import aiohttp
import pytest
from pytest_lazyfixture import lazy_fixture

from juno import (
    BadOrder, Balance, Candle, Depth, ExchangeInfo, OrderMissing, OrderType, Side, Ticker, Trade
)
from juno.asyncio import resolved_stream, zip_async
from juno.config import init_instance
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken
from juno.time import HOUR_MS, MIN_MS, strptimestamp, time_ms
from juno.typing import types_match


def parametrize_exchange(exchange_types: list[Type[Exchange]]):
    return pytest.mark.parametrize(
        'exchange',
        [lazy_fixture(e.__name__.lower()) for e in exchange_types],
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


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken])
async def test_get_exchange_info(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    info = await exchange.get_exchange_info()

    assert len(info.assets) > 0
    if '__all__' not in info.assets:
        assert info.assets['btc']

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
@parametrize_exchange([Binance])  # TODO: Add gateio?
async def test_map_tickers(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # Note, this is an expensive call!
    tickers = await exchange.map_tickers()

    assert len(tickers) > 0
    assert types_match(tickers, dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio?
async def test_map_one_ticker(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    tickers = await exchange.map_tickers(symbols=['eth-btc'])

    assert len(tickers) == 1
    assert types_match(tickers, dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio.
async def test_map_spot_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    balances = await exchange.map_balances(account='spot')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])  # TODO: Add coinbase, gateio, kraken
async def test_map_cross_margin_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    balances = await exchange.map_balances(account='margin')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_map_isolated_margin_balances(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)  # TODO: Add coinbase, gateio, kraken

    balances = await exchange.map_balances(account='isolated')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_get_max_borrowable(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)  # TODO: Add coinbase, gateio, kraken

    size = await exchange.get_max_borrowable(account='margin', asset='btc')

    assert types_match(size, Decimal)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase])  # TODO: Add gateio.
async def test_stream_historical_candles(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

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
@parametrize_exchange([Binance, Kraken])  # TODO: Add gateio.
async def test_connect_stream_candles(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    async with exchange.connect_stream_candles(symbol='eth-btc', interval=MIN_MS) as stream:
        async for candle in stream:
            assert types_match(candle, Candle)
            break


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, GateIO, Kraken])
async def test_get_depth(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    depth = await exchange.get_depth('eth-btc')

    assert types_match(depth, Depth.Snapshot)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken])
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
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
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
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
async def test_connect_stream_trades(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # FIAT pairs seem to be more active where supported.
    symbol = 'eth-btc' if isinstance(exchange, Binance) else 'eth-eur'

    async with exchange.connect_stream_trades(symbol=symbol) as stream:
        async for trade in stream:
            assert types_match(trade, Trade)
            break


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO])  # TODO: Add kraken
async def test_place_order_bad_order(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    with pytest.raises(BadOrder):
        await exchange.place_order(
            account='spot',
            symbol='eth-btc',
            side=Side.BUY,
            type_=OrderType.MARKET,
            size=Decimal('0.0'),
        )


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO])  # TODO: Add kraken
async def test_cancel_order_order_missing(loop, request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    with pytest.raises(OrderMissing):
        await exchange.cancel_order(
            account='spot',
            symbol='eth-btc',
            client_id='MWCF6FF1SducGg66c4aXtw==',
        )


def skip_not_configured(request, exchange):
    markers = ['exchange', 'manual']
    if request.config.option.markexpr not in markers:
        pytest.skip(f'Specify {"" or "".join(markers)} marker to run!')
    if not exchange:
        pytest.skip('Exchange params not configured')


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with init_instance(type_, config) as exchange:
            yield exchange
    except TypeError:
        yield None
