import math
import statistics
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, Overflow
from typing import Iterable, TypeVar

TNum = TypeVar("TNum", int, Decimal)

_YEAR_MS = 31_556_952_000


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def ceil_multiple_offset(value: TNum, multiple: TNum, offset: TNum) -> TNum:
    return ceil_multiple(value - offset, multiple) + offset


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


def floor_multiple_offset(value: TNum, multiple: TNum, offset: TNum) -> TNum:
    return floor_multiple(value - offset, multiple) + offset


def round_half_up(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_HALF_UP)


def round_down(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_DOWN)


def lerp(a: Decimal, b: Decimal, t: Decimal) -> Decimal:
    return t * a + (1 - t) * b


def minmax(values: Iterable[Decimal]) -> tuple[Decimal, Decimal]:
    min_ = Decimal("Inf")
    max_ = Decimal("-Inf")
    for value in values:
        min_ = min(min_, value)
        max_ = max(max_, value)
    return min_, max_


def split(total: Decimal, parts: int, precision: int) -> list[Decimal]:
    assert parts > 0

    if parts == 1:
        return [total]

    part = (total / parts).quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_DOWN)
    result = [part for _ in range(parts - 1)]
    result.append(total - sum(result))
    return result


def spans_overlap(span1: tuple[int, int], span2: tuple[int, int]) -> bool:
    for _ in range(max(span1[0], span2[0]), min(span1[-1], span2[-1])):
        return True
    return False


def rpstdev(data: Iterable[Decimal]) -> Decimal:
    """Square root of the population variance relative (%) to mean."""
    mean = statistics.mean(data)
    return statistics.pstdev(data) / mean


# Ref: https://www.investopedia.com/articles/basics/10/guide-to-calculating-roi.asp
# TODO: Move outside math module.
def annualized(duration: int, value: Decimal) -> Decimal:
    assert value >= -1
    n = Decimal(duration) / _YEAR_MS
    if n == 0:
        return Decimal("0.0")
    try:
        return (1 + value) ** (1 / n) - 1
    except Overflow:
        return Decimal("Inf")


def precision_to_decimal(precision: int) -> Decimal:
    if precision < 0:
        raise ValueError(f"Precision must be positive but got {precision}")
    if precision == 0:
        return Decimal("1.0")
    return Decimal("0." + (precision - 1) * "0" + "1")
