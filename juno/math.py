import math
from decimal import ROUND_DOWN, Decimal
from typing import TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


def adjust_size(size: Decimal, min_size: Decimal, max_size: Decimal, size_step: Decimal
                ) -> Decimal:
    if size < min_size:
        return Decimal(0)
    size = min(size, max_size)
    return size.quantize(size_step.normalize(), rounding=ROUND_DOWN)
