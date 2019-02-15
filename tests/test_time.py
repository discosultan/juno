from datetime import datetime, timezone

from juno import time


def test_datetime_timestamp_ms():
    output = time.datetime_timestamp_ms(datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert output == 946_684_800_000


def test_datetime_utcfromtimestamp_ms():
    output = time.datetime_utcfromtimestamp_ms(946_684_800_000)
    assert output == datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_strfinterval():
    output = time.strfinterval(time.DAY_MS * 2)
    assert output == '2d'


def test_strpinterval():
    output = time.strpinterval('2d')
    assert output == time.DAY_MS * 2
