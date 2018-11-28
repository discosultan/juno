from time import time


MS_SEC = 1000
MS_MIN = 60_000
MS_HOUR = 3_600_000
MS_DAY = 86_400_000
MS_YEAR = 31_556_952_000


def time_ms() -> int:
    """Returns current time since EPOCH in milliseconds"""
    return int(round(time() * 1000.0))
