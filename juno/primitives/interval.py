import re
from types import ModuleType

from ._aliases import Interval


class Interval_(ModuleType):
    SEC: Interval = 1000
    MIN: Interval = 60_000
    HOUR: Interval = 3_600_000
    DAY: Interval = 86_400_000
    WEEK: Interval = 604_800_000
    MONTH: Interval = 2_629_746_000
    YEAR: Interval = 31_556_952_000

    MIN_SEC = 60
    HOUR_SEC = 3600
    DAY_SEC = 86_400
    WEEK_SEC = 604_800
    MONTH_SEC = 2_629_746
    YEAR_SEC = 31_556_952

    @staticmethod
    def format(interval: Interval) -> str:
        result = ""
        remainder = interval
        for letter, factor in _INTERVAL_FACTORS.items():
            quotient, remainder = divmod(remainder, factor)
            if quotient > 0:
                result += f"{quotient}{letter}"
            if remainder == 0:
                break
        return result if result else "0ms"

    @staticmethod
    def parse(interval: str) -> Interval:
        result = 0
        for group in re.findall(r"(\d+[a-zA-Z]+)", interval):
            result += _calc_interval_group(group)
        return result


def _calc_interval_group(group: str) -> int:
    for i in range(1, len(group)):
        if group[i].isalpha():
            return int(group[:i]) * _INTERVAL_FACTORS[group[i:]]
    raise ValueError(f"Invalid interval group: {group}")


# Is assumed to be ordered by values descending.
_INTERVAL_FACTORS = {
    "y": Interval_.YEAR,
    "M": Interval_.MONTH,
    "w": Interval_.WEEK,
    "d": Interval_.DAY,
    "h": Interval_.HOUR,
    "m": Interval_.MIN,
    "s": Interval_.SEC,
    "ms": 1,
}
