from decimal import Decimal

import pytest

from juno import BadOrder, Balance, Depth, ExchangeInfo, OrderMissing, OrderType, Side, Ticker
from juno.asyncio import resolved_stream, zip_async
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken
from juno.typing import types_match
from tests.exchanges import parametrize_exchange, skip_not_configured


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken])
async def test_get_exchange_info(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    info = await exchange_session.get_exchange_info()

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
async def test_map_tickers(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    # Note, this is an expensive call!
    tickers = await exchange_session.map_tickers()

    assert len(tickers) > 0
    assert types_match(tickers, dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio?
async def test_map_one_ticker(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    tickers = await exchange_session.map_tickers(symbols=['eth-btc'])

    assert len(tickers) == 1
    assert types_match(tickers, dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio.
async def test_map_spot_balances(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    balances = await exchange_session.map_balances(account='spot')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])  # TODO: Add coinbase, gateio, kraken
async def test_map_cross_margin_balances(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    balances = await exchange_session.map_balances(account='margin')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_map_isolated_margin_balances(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)  # TODO: Add coinbase, gateio, kraken

    balances = await exchange_session.map_balances(account='isolated')
    assert types_match(balances, dict[str, dict[str, Balance]])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])
async def test_get_max_borrowable(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)  # TODO: Add coinbase, gateio, kraken

    size = await exchange_session.get_max_borrowable(account='margin', asset='btc')

    assert types_match(size, Decimal)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, GateIO, Kraken])
async def test_get_depth(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    depth = await exchange_session.get_depth('eth-btc')

    assert types_match(depth, Depth.Snapshot)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken])
async def test_connect_stream_depth(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    expected_types = (
        [Depth.Snapshot, Depth.Update] if exchange_session.can_stream_depth_snapshot
        else [Depth.Update]
    )

    async with exchange_session.connect_stream_depth('eth-btc') as stream:
        async for depth, expected_type in zip_async(stream, resolved_stream(*expected_types)):
            assert types_match(depth, expected_type)


@pytest.mark.exchange
@pytest.mark.manual
# TODO: Add kraken and gateio (if find out how to place market order)
@parametrize_exchange([Binance, Coinbase])
async def test_place_order_bad_order(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    with pytest.raises(BadOrder):
        await exchange_session.place_order(
            account='spot',
            symbol='eth-btc',
            side=Side.BUY,
            type_=OrderType.MARKET,
            size=Decimal('0.0'),
        )


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO])  # TODO: Add kraken
async def test_cancel_order_order_missing(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    with pytest.raises(OrderMissing):
        await exchange_session.cancel_order(
            account='spot',
            symbol='eth-btc',
            client_id=exchange_session.generate_client_id(),
        )
