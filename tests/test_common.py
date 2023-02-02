from decimal import Decimal

import pytest

from juno import Interval_, Timestamp_
from juno.common import Candle, Fill


@pytest.mark.parametrize(
    "previous,current,expected_output",
    [
        # Data taken from https://school.stockcharts.com/doku.php?id=chart_analysis:heikin_ashi:
        [
            Candle(
                time=Timestamp_.parse("2011-08-01"),
                open=Decimal("58.67"),
                high=Decimal("58.82"),
                low=Decimal("57.03"),
                close=Decimal("58.06"),
            ),
            Candle(
                time=Timestamp_.parse("2011-08-02"),
                open=Decimal("57.46"),
                high=Decimal("57.72"),
                low=Decimal("56.21"),
                close=Decimal("56.27"),
            ),
            Candle(
                time=Timestamp_.parse("2011-08-02"),
                open=Decimal("58.37"),
                high=Decimal("58.37"),
                low=Decimal("56.21"),
                close=Decimal("56.92"),
            ),
        ],
        [
            Candle(
                time=Timestamp_.parse("2011-08-02"),
                open=Decimal("58.37"),
                high=Decimal("58.37"),
                low=Decimal("56.21"),
                close=Decimal("56.92"),
            ),
            Candle(
                time=Timestamp_.parse("2011-08-03"),
                open=Decimal("56.37"),
                high=Decimal("56.88"),
                low=Decimal("55.35"),
                close=Decimal("56.81"),
            ),
            Candle(
                time=Timestamp_.parse("2011-08-03"),
                open=Decimal("57.64"),
                high=Decimal("57.64"),
                low=Decimal("55.35"),
                close=Decimal("56.35"),
            ),
        ],
        # When using the method brought out at
        # https://thetradingbible.com/how-to-read-heikin-ashi-candles, the following test data can
        # be used:
        #
        # [
        #     Candle(
        #         open=Decimal("10.00"),
        #         high=Decimal("19.00"),
        #         low=Decimal("8.00"),
        #         close=Decimal("17.00"),
        #     ),
        #     Candle(
        #         open=Decimal("17.00"),
        #         high=Decimal("20.00"),
        #         low=Decimal("16.00"),
        #         close=Decimal("19.00"),
        #     ),
        #     Candle(
        #         open=Decimal("13.50"),
        #         high=Decimal("20.00"),
        #         low=Decimal("16.00"),
        #         close=Decimal("18.00"),
        #     ),
        # ],
    ],
)
def test_heikin_ashi(previous: Candle, current: Candle, expected_output: Candle) -> None:
    output = Candle.heikin_ashi(previous, current)
    _assert_candle(output, expected_output, tolerance=10**-2)


def test_gen_heikin_ashi() -> None:
    # Data taken from TradingView:
    # - input = binance btc-usdt 1d regular 2017-08-17 - 2017-08-24
    # - expected_output = binance btc-usdt 1d heikin-ashi 2017-08-17 - 2017-08-24
    input = [
        Candle(
            time=Timestamp_.parse("2017-08-17"),
            open=Decimal("4261.48"),
            high=Decimal("4485.39"),
            low=Decimal("4200.74"),
            close=Decimal("4285.08"),
            volume=Decimal("795"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-18"),
            open=Decimal("4285.08"),
            high=Decimal("4371.52"),
            low=Decimal("3938.77"),
            close=Decimal("4108.37"),
            volume=Decimal("1200"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-19"),
            open=Decimal("4108.37"),
            high=Decimal("4184.69"),
            low=Decimal("3850.00"),
            close=Decimal("4139.98"),
            volume=Decimal("381"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-20"),
            open=Decimal("4120.98"),
            high=Decimal("4211.08"),
            low=Decimal("4032.62"),
            close=Decimal("4086.29"),
            volume=Decimal("467"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-21"),
            open=Decimal("4069.13"),
            high=Decimal("4119.62"),
            low=Decimal("3911.79"),
            close=Decimal("4016.00"),
            volume=Decimal("692"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-22"),
            open=Decimal("4016.00"),
            high=Decimal("4104.82"),
            low=Decimal("3400.00"),
            close=Decimal("4040.00"),
            volume=Decimal("967"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-23"),
            open=Decimal("4040.00"),
            high=Decimal("4265.80"),
            low=Decimal("4013.89"),
            close=Decimal("4114.01"),
            volume=Decimal("1001"),
        ),
    ]
    expected_output = [
        Candle(
            time=Timestamp_.parse("2017-08-17"),
            open=Decimal("4273.28"),
            high=Decimal("4485.39"),
            low=Decimal("4200.74"),
            close=Decimal("4308.17"),
            volume=Decimal("795"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-18"),
            open=Decimal("4290.73"),
            high=Decimal("4371.52"),
            low=Decimal("3938.77"),
            close=Decimal("4175.94"),
            volume=Decimal("1200"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-19"),
            open=Decimal("4233.33"),
            high=Decimal("4233.33"),
            low=Decimal("3850.00"),
            close=Decimal("4070.76"),
            volume=Decimal("381"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-20"),
            open=Decimal("4152.05"),
            high=Decimal("4211.08"),
            low=Decimal("4032.62"),
            close=Decimal("4112.74"),
            volume=Decimal("467"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-21"),
            open=Decimal("4132.39"),
            high=Decimal("4132.39"),
            low=Decimal("3911.79"),
            close=Decimal("4029.14"),
            volume=Decimal("692"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-22"),
            open=Decimal("4080.76"),
            high=Decimal("4104.82"),
            low=Decimal("3400.00"),
            close=Decimal("3890.21"),
            volume=Decimal("967"),
        ),
        Candle(
            time=Timestamp_.parse("2017-08-23"),
            open=Decimal("3985.48"),
            high=Decimal("4265.80"),
            low=Decimal("3985.48"),
            close=Decimal("4108.42"),
            volume=Decimal("1001"),
        ),
    ]

    gen_heikin_ashi = Candle.gen_heikin_ashi(Interval_.DAY)
    for input_candle, expected_output_candle in zip(input, expected_output):
        next(gen_heikin_ashi)
        output_candle = gen_heikin_ashi.send(input_candle)
        _assert_candle(output_candle, expected_output_candle, tolerance=10**-2)


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


def _assert_candle(obtained: Candle, expected: Candle, tolerance: float) -> None:
    assert obtained.time == expected.time
    assert obtained.open == pytest.approx(expected.open, abs=tolerance)
    assert obtained.high == pytest.approx(expected.high, abs=tolerance)
    assert obtained.low == pytest.approx(expected.low, abs=tolerance)
    assert obtained.close == pytest.approx(expected.close, abs=tolerance)
    assert obtained.volume == expected.volume
