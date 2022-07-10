from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Type

import aiohttp
import pytest
import pytest_asyncio
from asyncstdlib import zip as zip_async
from pytest_lazyfixture import lazy_fixture

from juno import (
    BadOrder,
    Balance,
    Candle,
    Depth,
    ExchangeInfo,
    Interval_,
    OrderMissing,
    OrderType,
    SavingsProduct,
    Side,
    Ticker,
    Timestamp_,
    Trade,
    exchanges,
)
from juno.asyncio import resolved_stream
from juno.config import init_instance
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken, KuCoin
from juno.inspect import list_concretes_from_module
from juno.typing import types_match

exchange_type_fixtures = {
    e: lazy_fixture(e.__name__.lower()) for e in list_concretes_from_module(exchanges, Exchange)
}


def parametrize_exchange(exchange_types: list[Type[Exchange]]):
    return pytest.mark.parametrize(
        "exchange",
        [exchange_type_fixtures[e] for e in exchange_types],
        ids=[e.__name__ for e in exchange_types],
    )


# We use a session-scoped loop for shared rate-limiting.
@pytest.fixture(scope="module")
def event_loop():
    with aiohttp.test_utils.loop_context() as loop:
        yield loop


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="module")
async def binance(config):
    async with try_init_exchange(Binance, config) as exchange:
        yield exchange


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="module")
async def coinbase(config):
    async with try_init_exchange(Coinbase, config) as exchange:
        yield exchange


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="module")
async def gateio(config):
    async with try_init_exchange(GateIO, config) as exchange:
        yield exchange


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="module")
async def kraken(config):
    async with try_init_exchange(Kraken, config) as exchange:
        yield exchange


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="module")
async def kucoin(config):
    async with try_init_exchange(KuCoin, config) as exchange:
        yield exchange


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken, KuCoin])
async def test_get_exchange_info(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    info = await exchange.get_exchange_info()

    assert len(info.assets) > 0
    if "__all__" not in info.assets:
        assert info.assets["btc"]

    assert len(info.fees) > 0
    first_fees = next(iter(info.fees.values()))
    assert 0 <= first_fees.taker <= Decimal("0.1")
    assert 0 <= first_fees.maker <= Decimal("0.1")
    assert -4 <= first_fees.taker.as_tuple().exponent <= -1
    assert -4 <= first_fees.maker.as_tuple().exponent <= -1
    if "__all__" not in info.fees:
        assert info.fees["eth-btc"]

    assert len(info.filters) > 0
    if "__all__" not in info.filters:
        assert info.filters["eth-btc"]

    assert types_match(info, ExchangeInfo)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])  # TODO: Add gateio?
async def test_map_tickers(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # Note, this is an expensive call!
    tickers = await exchange.map_tickers()

    assert len(tickers) > 0
    assert types_match(tickers, dict[str, Ticker])
    assert "eth-btc" in tickers


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio?
async def test_map_one_ticker(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    tickers = await exchange.map_tickers(symbols=["eth-btc"])

    assert len(tickers) == 1
    assert types_match(tickers, dict[str, Ticker])
    assert "eth-btc" in tickers


@pytest.mark.exchange
@pytest.mark.manual
async def test_kraken_map_one_newer_ticker(request, kraken: Kraken) -> None:
    skip_not_configured(request, kraken)

    # Kraken uses different notation for older vs newer symbols.
    # For example: XETHXXBT vs ADAXBT.
    # Hence the need for this additional test.

    tickers = await kraken.map_tickers(symbols=["ada-btc"])

    assert len(tickers) == 1
    assert "ada-btc" in tickers


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken, KuCoin])  # TODO: Add gateio.
async def test_map_spot_balances(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    balances = await exchange.map_balances(account="spot")
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])  # TODO: Add coinbase, gateio, kraken
async def test_map_cross_margin_balances(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    balances = await exchange.map_balances(account="margin")
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_map_isolated_margin_balances(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)  # TODO: Add coinbase, gateio, kraken

    balances = await exchange.map_balances(account="isolated")
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_get_max_borrowable(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)  # TODO: Add coinbase, gateio, kraken

    size = await exchange.get_max_borrowable(account="margin", asset="btc")

    assert types_match(size, Decimal)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase])  # TODO: Add gateio.
async def test_stream_historical_candles(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    start = Timestamp_.parse("2018-01-01")

    count = 0
    async for candle in exchange.stream_historical_candles(
        symbol="eth-btc", interval=Interval_.HOUR, start=start, end=start + Interval_.HOUR
    ):
        if count == 1:
            pytest.fail("Expected a single candle")
        count += 1

        assert types_match(candle, Candle)
        assert candle.time == start


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Kraken])  # TODO: Add gateio.
async def test_connect_stream_candles(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    async with exchange.connect_stream_candles(symbol="eth-btc", interval=Interval_.MIN) as stream:
        async for candle in stream:
            assert types_match(candle, Candle)
            break


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, GateIO, KuCoin])
async def test_get_depth(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    depth = await exchange.get_depth("eth-btc")

    assert types_match(depth, Depth.Snapshot)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken, KuCoin])
async def test_connect_stream_depth(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    expected_types = (
        [Depth.Snapshot, Depth.Update] if exchange.can_stream_depth_snapshot else [Depth.Update]
    )

    async with exchange.connect_stream_depth("eth-btc") as stream:
        async for depth, expected_type in zip_async(stream, resolved_stream(*expected_types)):
            assert types_match(depth, expected_type)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
async def test_stream_historical_trades(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # Coinbase can only stream from most recent, hence we use current time.
    if isinstance(exchange, Coinbase):
        end = Timestamp_.now()
        start = end - 5 * Interval_.MIN
    else:
        start = Timestamp_.parse("2018-01-01")
        end = start + Interval_.HOUR

    stream = exchange.stream_historical_trades(symbol="eth-btc", start=start, end=end)
    async for trade in stream:
        assert types_match(trade, Trade)
        assert trade.time >= start
        break


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
async def test_connect_stream_trades(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    # FIAT pairs seem to be more active where supported.
    symbol = "eth-btc" if isinstance(exchange, Binance) else "eth-eur"

    async with exchange.connect_stream_trades(symbol=symbol) as stream:
        async for trade in stream:
            assert types_match(trade, Trade)
            break


@pytest.mark.exchange
@pytest.mark.manual
# TODO: Add kraken and gateio (if find out how to place market order)
@parametrize_exchange([Binance, Coinbase, KuCoin])
async def test_place_order_bad_order(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    with pytest.raises(BadOrder):
        await exchange.place_order(
            account="spot",
            symbol="eth-btc",
            side=Side.BUY,
            type_=OrderType.MARKET,
            size=Decimal("0.0"),
        )


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Kraken])
async def test_edit_order_order_missing(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    with pytest.raises(OrderMissing):
        await exchange.edit_order(
            existing_id=exchange.generate_client_id(),
            account="spot",
            symbol="eth-btc",
            type_=OrderType.LIMIT,
            size=Decimal("1.0"),
            price=Decimal("1.0"),
        )


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken, KuCoin])
async def test_cancel_order_order_missing(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    with pytest.raises(OrderMissing):
        await exchange.cancel_order(
            account="spot",
            symbol="eth-btc",
            client_id=exchange.generate_client_id(),
        )


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_get_deposit_address(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    address = await exchange.get_deposit_address("btc")
    assert type(address) is str


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_map_savings_products(request, exchange: Exchange) -> None:
    skip_not_configured(request, exchange)

    savings_products = await exchange.map_savings_products()
    assert types_match(savings_products, dict[str, SavingsProduct])


def skip_not_configured(request, exchange):
    markers = ["exchange", "manual"]
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    if not exchange:
        pytest.skip("Exchange params not configured")


@asynccontextmanager
async def try_init_exchange(type_, config):
    try:
        async with init_instance(type_, config) as exchange:
            yield exchange
    except TypeError:
        yield None
