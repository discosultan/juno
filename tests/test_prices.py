from decimal import Decimal

import pytest

from juno import Candle, Symbol_
from juno.components import Prices

from . import fakes


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
async def test_map_asset_prices(symbols, chandler_symbols, expected_output) -> None:
    candles = [
        Candle(time=0, open=Decimal("2.0"), close=Decimal("1.0")),
        Candle(time=1, close=Decimal("2.0")),
        Candle(time=2, close=Decimal("3.0")),
    ]
    prices = Prices(
        informant=fakes.Informant(symbols=chandler_symbols),
        chandler=fakes.Chandler(candles={("exchange", s, 1): candles for s in chandler_symbols}),
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
