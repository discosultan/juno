from datetime import datetime, timezone

import pytest

from juno.primitives.interval import Interval, Interval_
from juno.primitives.timestamp import Timestamp, Timestamp_


def test_from_datetime_utc() -> None:
    output = Timestamp_.from_datetime_utc(datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert output == 946_684_800_000


def test_to_datetime_utc() -> None:
    output = Timestamp_.to_datetime_utc(946_684_800_000)
    assert output == datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_format():
    assert Timestamp_.format(1546300800000) == "2019-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        ["2019-01-01", 1546300800000],
        ["2019-01-01T00:00:00Z", 1546300800000],
        ["2019-01-01T00:00:00+00:00", 1546300800000],
    ],
)
def test_parse(input_: str, expected_output: int) -> None:
    assert Timestamp_.parse(input_) == expected_output


@pytest.mark.parametrize(
    "timestamp,interval,expected_output",
    [
        [1, Interval_.SEC, Interval_.SEC],
        [1001, Interval_.DAY, Interval_.DAY],
        # 2020-01-01T00:00:00Z -> 2020-01-06T00:00:00Z
        [1577836800000, Interval_.WEEK, 1578268800000],
        # 2020-01-02T00:00:00Z -> 2020-02-01T00:00:00Z
        [1577923200000, Interval_.MONTH, 1580515200000],
    ],
)
def test_ceil(timestamp: Timestamp, interval: Interval, expected_output: int) -> None:
    assert Timestamp_.ceil(timestamp, interval) == expected_output


@pytest.mark.parametrize(
    "timestamp,interval,expected_output",
    [
        [1, Interval_.SEC, 0],
        [1001, Interval_.DAY, 0],
        # 2020-01-01T00:00:00Z -> 2019-12-30T00:00:00Z
        [1577836800000, Interval_.WEEK, 1577664000000],
        # 2020-01-02T00:00:00Z -> 2020-01-01T00:00:00Z
        [1577923200000, Interval_.MONTH, 1577836800000],
    ],
)
def test_floor(timestamp: Timestamp, interval: Interval, expected_output: int) -> None:
    assert Timestamp_.floor(timestamp, interval) == expected_output


@pytest.mark.parametrize(
    "timestamp,interval,expected_output",
    [
        [1, 1, True],
        [Interval_.SEC, Interval_.SEC, True],
        [Interval_.SEC, Interval_.MIN, False],
    ],
)
def test_is_in_interval(timestamp: Timestamp, interval: Interval, expected_output: bool) -> None:
    assert Timestamp_.is_in_interval(timestamp, interval) == expected_output
