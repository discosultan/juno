from datetime import datetime, timedelta, timezone
from time import time
from types import ModuleType

from juno.math import ceil_multiple, ceil_multiple_offset, floor_multiple, floor_multiple_offset

from ._aliases import Interval, Timestamp
from .interval import Interval_

_WEEK_OFFSET_MS = 345_600_000


class Timestamp_(ModuleType):
    MAX_TIME: Timestamp = 3_000_000_000_000  # 2065-01-24 05:20

    @staticmethod
    def now() -> Timestamp:
        """Returns current time since EPOCH in milliseconds."""
        return int(round(time() * 1000.0))
        # seconds = datetime.timestamp().replace(tzinfo=timezone.utc).timestamp()
        # return int(round(seconds * 1000.0))

    @staticmethod
    def from_datetime_utc(dt: datetime) -> Timestamp:
        assert dt.tzinfo == timezone.utc
        return int(round(dt.timestamp() * 1000.0))

    @staticmethod
    def to_datetime_utc(ms: Timestamp) -> datetime:
        return datetime.utcfromtimestamp(ms / 1000.0).replace(tzinfo=timezone.utc)

    @staticmethod
    def format_span(start: Timestamp, end: Timestamp) -> str:
        return f"{Timestamp_.to_datetime_utc(start)} - " f"{Timestamp_.to_datetime_utc(end)}"

    @staticmethod
    def format(timestamp: Timestamp) -> str:
        return Timestamp_.to_datetime_utc(timestamp).isoformat()

    @staticmethod
    def parse(timestamp: str) -> Timestamp:
        # Naive is handled as UTC.
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return Timestamp_.from_datetime_utc(dt)

    @staticmethod
    def floor(timestamp: Timestamp, interval: Interval) -> Timestamp:
        if interval < Interval_.WEEK:
            return floor_multiple(timestamp, interval)
        if interval == Interval_.WEEK:
            return floor_multiple_offset(timestamp, interval, _WEEK_OFFSET_MS)
        if interval == Interval_.MONTH:
            dt = Timestamp_.to_datetime_utc(timestamp)
            return Timestamp_.from_datetime_utc(
                dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            )
        raise NotImplementedError()

    @staticmethod
    def ceil(timestamp: Timestamp, interval: Interval) -> Timestamp:
        if interval < Interval_.WEEK:
            return ceil_multiple(timestamp, interval)
        if interval == Interval_.WEEK:
            return ceil_multiple_offset(timestamp, interval, _WEEK_OFFSET_MS)
        if interval == Interval_.MONTH:
            dt = Timestamp_.to_datetime_utc(timestamp)
            return Timestamp_.from_datetime_utc(
                (dt.replace(day=1) + timedelta(days=32)).replace(day=1)
            )
        raise NotImplementedError()

    @staticmethod
    def is_in_interval(timestamp: Timestamp, interval: Interval) -> bool:
        if interval < Interval_.WEEK:
            return timestamp % interval == 0
        if interval == Interval_.WEEK:
            return (timestamp % interval) - _WEEK_OFFSET_MS == 0
        raise NotImplementedError()
