import re
from datetime import datetime
from time import time

from dateutil.parser import isoparse
from dateutil.tz import UTC

SEC_MS = 1000
MIN_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
WEEK_MS = 604_800_000
MONTH_MS = 2_629_746_000
YEAR_MS = 31_556_952_000

MIN_SEC = 60
HOUR_SEC = 3600
DAY_SEC = 86_400

MAX_TIME_MS = 3_000_000_000_000  # 2065-01-24 05:20


def time_ms() -> int:
    """Returns current time since EPOCH in milliseconds."""
    return int(round(time() * 1000.0))
    # seconds = datetime.timestamp().replace(tzinfo=timezone.utc).timestamp()
    # return int(round(seconds * 1000.0))


def datetime_timestamp_ms(dt: datetime) -> int:
    assert dt.tzinfo == UTC
    return int(round(dt.timestamp() * 1000.0))


def datetime_utcfromtimestamp_ms(ms: int) -> datetime:
    return datetime.utcfromtimestamp(ms / 1000.0).replace(tzinfo=UTC)


# Is assumed to be ordered by values descending.
_INTERVAL_FACTORS = {
    'y': YEAR_MS,
    'M': MONTH_MS,
    'w': WEEK_MS,
    'd': DAY_MS,
    'h': HOUR_MS,
    'm': MIN_MS,
    's': SEC_MS,
    'ms': 1,
}


def strfinterval(interval: int) -> str:
    result = ''
    remainder = interval
    for letter, factor in _INTERVAL_FACTORS.items():
        quotient, remainder = divmod(remainder, factor)
        if quotient > 0:
            result += f'{quotient}{letter}'
        if remainder == 0:
            break
    return result if result else '0ms'


def strpinterval(interval: str) -> int:
    result = 0
    for group in re.findall(r'(\d+[a-zA-Z]+)', interval):
        result += _calc_interval_group(group)
    return result


def _calc_interval_group(group: str) -> int:
    for i in range(1, len(group)):
        if group[i].isalpha():
            return int(group[:i]) * _INTERVAL_FACTORS[group[i:]]
    raise ValueError(f'Invalid interval group: {group}')


def strfspan(start: int, end: int) -> str:
    return f'{datetime_utcfromtimestamp_ms(start)} - {datetime_utcfromtimestamp_ms(end)}'


def strftimestamp(timestamp: int) -> str:
    return str(datetime_utcfromtimestamp_ms(timestamp))


def strptimestamp(timestamp: str) -> int:
    # Naive is handled as UTC.
    dt = isoparse(timestamp)
    if dt.tzinfo:
        dt = dt.astimezone(UTC)
    else:
        dt = dt.replace(tzinfo=UTC)
    return datetime_timestamp_ms(dt)
