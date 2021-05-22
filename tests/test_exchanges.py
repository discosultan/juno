from decimal import Decimal

import pytest

from juno import BadOrder, Balance, Depth, OrderMissing, OrderType, Side
from juno.asyncio import resolved_stream, zip_async
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken
from juno.typing import types_match
from tests.exchanges import parametrize_exchange, skip_not_configured


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
