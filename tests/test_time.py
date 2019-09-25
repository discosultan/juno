from datetime import datetime

import pytest

from juno import time


def test_datetime_timestamp_ms():
    output = time.datetime_timestamp_ms(datetime(2000, 1, 1, tzinfo=time.UTC))
    assert output == 946_684_800_000


def test_datetime_utcfromtimestamp_ms():
    output = time.datetime_utcfromtimestamp_ms(946_684_800_000)
    assert output == datetime(2000, 1, 1, tzinfo=time.UTC)


@pytest.mark.parametrize(
    'input,expected_output', [
        [time.DAY_MS * 2, '2d'],
        [123, '123ms'],
        [1234, '1s234ms'],
        [0, '0ms'],
    ]
)
def test_strfinterval(input, expected_output):
    assert time.strfinterval(input) == expected_output


def test_strpinterval():
    output = time.strpinterval('2d')
    assert output == time.DAY_MS * 2
