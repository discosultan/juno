from datetime import datetime

import pytest

from juno import time


def test_datetime_timestamp_ms() -> None:
    output = time.datetime_timestamp_ms(datetime(2000, 1, 1, tzinfo=time.UTC))
    assert output == 946_684_800_000


def test_datetime_utcfromtimestamp_ms() -> None:
    output = time.datetime_utcfromtimestamp_ms(946_684_800_000)
    assert output == datetime(2000, 1, 1, tzinfo=time.UTC)


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        [time.DAY_MS * 2, "2d"],
        [123, "123ms"],
        [1234, "1s234ms"],
        [0, "0ms"],
    ],
)
def test_strfinterval(input_, expected_output) -> None:
    assert time.strfinterval(input_) == expected_output


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        ["1d", time.DAY_MS],
        ["2d", time.DAY_MS * 2],
        ["1s1ms", time.SEC_MS + 1],
        ["1m1s", time.MIN_MS + time.SEC_MS],
    ],
)
def test_strpinterval(input_, expected_output) -> None:
    output = time.strpinterval(input_)
    assert output == expected_output


def test_strftimestamp():
    assert time.strftimestamp(1546300800000) == "2019-01-01 00:00:00+00:00"


def test_strptimestamp() -> None:
    assert time.strptimestamp("2019-01-01") == 1546300800000


@pytest.mark.parametrize(
    "timestamp,interval,expected_output",
    [
        [1, time.SEC_MS, time.SEC_MS],
        [1001, time.DAY_MS, time.DAY_MS],
        # 2020-01-01T00:00:00Z -> 2020-01-06T00:00:00Z
        [1577836800000, time.WEEK_MS, 1578268800000],
        # 2020-01-02T00:00:00Z -> 2020-02-01T00:00:00Z
        [1577923200000, time.MONTH_MS, 1580515200000],
    ],
)
def test_ceil_timestamp(timestamp: int, interval: int, expected_output: int) -> None:
    assert time.ceil_timestamp(timestamp, interval) == expected_output


@pytest.mark.parametrize(
    "timestamp,interval,expected_output",
    [
        [1, time.SEC_MS, 0],
        [1001, time.DAY_MS, 0],
        # 2020-01-01T00:00:00Z -> 2019-12-30T00:00:00Z
        [1577836800000, time.WEEK_MS, 1577664000000],
        # 2020-01-02T00:00:00Z -> 2020-01-01T00:00:00Z
        [1577923200000, time.MONTH_MS, 1577836800000],
    ],
)
def test_floor_timestamp(timestamp: int, interval: int, expected_output: int) -> None:
    assert time.floor_timestamp(timestamp, interval) == expected_output
