from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from juno import Asset, Candle, Symbol, Symbol_
from juno.components import Prices
from juno.components.prices import InsufficientPrices
from tests.mocks import mock_chandler, mock_informant


@pytest.mark.parametrize(
    "symbols,chandler_symbols,expected_output",
    [
        # Basic.
        (
            ["eth-btc"],
            ["eth-btc", "btc-usdt"],
            {
                "eth": [Decimal("4.0"), Decimal("1.0"), Decimal("4.0"), Decimal("9.0")],
                "btc": [Decimal("2.0"), Decimal("1.0"), Decimal("2.0"), Decimal("3.0")],
            },
        ),
        # Fiat as quote.
        (
            ["btc-usdt"],
            ["btc-usdt"],
            {
                "btc": [Decimal("2.0"), Decimal("1.0"), Decimal("2.0"), Decimal("3.0")],
                "usdt": [Decimal("1.0"), Decimal("1.0"), Decimal("1.0"), Decimal("1.0")],
            },
        ),
        # Combined.
        (
            ["eth-btc", "btc-usdt"],
            ["eth-btc", "btc-usdt"],
            {
                "eth": [Decimal("4.0"), Decimal("1.0"), Decimal("4.0"), Decimal("9.0")],
                "btc": [Decimal("2.0"), Decimal("1.0"), Decimal("2.0"), Decimal("3.0")],
                "usdt": [Decimal("1.0"), Decimal("1.0"), Decimal("1.0"), Decimal("1.0")],
            },
        ),
    ],
)
async def test_map_asset_prices(
    mocker: MockerFixture,
    symbols: list[Symbol],
    chandler_symbols: list[Symbol],
    expected_output: dict[Asset, Decimal],
) -> None:
    candles = [
        Candle(time=0, open=Decimal("2.0"), close=Decimal("1.0")),
        Candle(time=1, close=Decimal("2.0")),
        Candle(time=2, close=Decimal("3.0")),
    ]
    prices = Prices(
        informant=mock_informant(mocker, symbols=chandler_symbols),
        chandler=mock_chandler(
            mocker,
            candles=candles,
            first_candle=candles[0],
            last_candle=candles[-1],
        ),
    )
    output = await prices.map_asset_prices(
        exchange="exchange",
        assets=Symbol_.iter_assets(symbols),
        interval=1,
        target_asset="usdt",
        start=0,
        end=3,
    )
    assert output == expected_output


async def test_map_asset_prices_insufficient_prices(mocker: MockerFixture) -> None:
    prices = Prices(
        informant=mock_informant(mocker, symbols=["btc-usdt"]),
        chandler=mock_chandler(
            mocker,
            candles=[Candle(time=1)],
            first_candle=Candle(time=1),
            last_candle=Candle(time=1),
        ),
    )
    with pytest.raises(InsufficientPrices):
        await prices.map_asset_prices(
            exchange="exchange",
            assets=["btc"],
            interval=1,
            target_asset="usdt",
            start=0,
            end=3,
        )
