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
    'input_,expected_output', [
        [time.DAY_MS * 2, '2d'],
        [123, '123ms'],
        [1234, '1s234ms'],
        [0, '0ms'],
    ]
)
def test_strfinterval(input_, expected_output) -> None:
    assert time.strfinterval(input_) == expected_output


def test_strftimestamp():
    assert time.strftimestamp(1546300800000) == '2019-01-01 00:00:00+00:00'


@pytest.mark.parametrize(
    'input_,expected_output', [
        ['1d', time.DAY_MS],
        ['2d', time.DAY_MS * 2],
    ]
)
def test_strpinterval(input_, expected_output) -> None:
    output = time.strpinterval(input_)
    assert output == expected_output


def test_strptimestamp() -> None:
    assert time.strptimestamp('2019-01-01') == 1546300800000
