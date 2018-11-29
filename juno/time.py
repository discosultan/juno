from datetime import datetime
from time import time


SEC_MS = 1000
MIN_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
WEEK_MS = 604_800_000
MONTH_MS = 2_629_746_000
YEAR_MS = 31_556_952_000


def time_ms() -> int:
    """Returns current time since EPOCH in milliseconds"""
    return int(round(time() * 1000.0))


def datetime_timestamp_ms(dt: datetime) -> int:
    return int(round(dt.timestamp() * 1000.0))


def datetime_fromtimestamp_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0)
