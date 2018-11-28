import math


def ceil_multiple(value: int, multiple: int) -> int:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: int, multiple: int) -> int:
    return value - (value % multiple)
