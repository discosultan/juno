from datetime import datetime, timezone

SEC_MS = 1000
MIN_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
WEEK_MS = 604_800_000
MONTH_MS = 2_629_746_000
YEAR_MS = 31_556_952_000

MAX_TIME_MS = 3000000000000  # Year 2065.


def time_ms() -> int:
    """Returns current time since EPOCH in milliseconds."""
    seconds = datetime.now().replace(tzinfo=timezone.utc).timestamp()
    return int(round(seconds * 1000.0))


def datetime_timestamp_ms(dt: datetime) -> int:
    assert dt.tzinfo == timezone.utc
    return int(round(dt.timestamp() * 1000.0))


def datetime_utcfromtimestamp_ms(ms: int) -> datetime:
    return datetime.utcfromtimestamp(ms / 1000.0).replace(tzinfo=timezone.utc)


# Is assumed to be ordered by values descending.
_INTERVAL_FACTORS = {
    'y': YEAR_MS,
    'M': MONTH_MS,
    'w': WEEK_MS,
    'd': DAY_MS,
    'h': HOUR_MS,
    'm': MIN_MS,
    's': SEC_MS
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
    return result


def strpinterval(interval: str) -> int:
    return int(interval[:-1]) * _INTERVAL_FACTORS[interval[-1]]
