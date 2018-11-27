from time import time


def time_ms() -> int:
    """Returns current time since EPOCH in milliseconds"""
    return int(round(time() * 1000.0))
