from decimal import Decimal

import pytest

from juno.common import Candle, Fill


# Ref: https://thetradingbible.com/how-to-read-heikin-ashi-candles
@pytest.mark.parametrize(
    "previous,current,expected_output",
    [
        [
            Candle(
                open=Decimal("10.00"),
                high=Decimal("19.00"),
                low=Decimal("8.00"),
                close=Decimal("17.00"),
            ),
            Candle(
                open=Decimal("17.00"),
                high=Decimal("20.00"),
                low=Decimal("16.00"),
                close=Decimal("19.00"),
            ),
            Candle(
                open=Decimal("13.50"),
                high=Decimal("20.00"),
                low=Decimal("16.00"),
                close=Decimal("18.00"),
            ),
        ],
    ],
)
def test_heikin_ashi(previous: Candle, current: Candle, expected_output: Candle) -> None:
    assert Candle.heikin_ashi(previous, current) == expected_output


def test_fill_from_cumulative() -> None:
    assert Fill.from_cumulative(
        fills=[
            Fill(
                price=Decimal("1.0"),
                size=Decimal("1.0"),
                quote=Decimal("1.0"),
                fee=Decimal("0.1"),
                fee_asset="btc",
            ),
        ],
        price=Decimal("1.0"),
        cumulative_size=Decimal("1.5"),
        cumulative_quote=Decimal("1.5"),
        cumulative_fee=Decimal("0.15"),
        fee_asset="btc",
    ) == Fill(
        price=Decimal("1.0"),
        size=Decimal("0.5"),
        quote=Decimal("0.5"),
        fee=Decimal("0.05"),
        fee_asset="btc",
    )
