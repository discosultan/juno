from decimal import Decimal

import pytest

from juno.common import Candle


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
