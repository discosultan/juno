import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Iterable, List, Tuple, TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


def round_half_up(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_HALF_UP)


def round_down(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_DOWN)


def minmax(values: Iterable[Decimal]) -> Tuple[Decimal, Decimal]:
    min_ = Decimal('Inf')
    max_ = Decimal('-Inf')
    for value in values:
        min_ = min(min_, value)
        max_ = max(max_, value)
    return min_, max_


def split(total: Decimal, parts: int) -> List[Decimal]:
    assert parts > 0

    if parts == 1:
        return [total]

    part = (total / parts).quantize(total, rounding=ROUND_DOWN)
    result = [part for _ in range(parts - 1)]
    result.append(total - sum(result))
    return result


def spans_overlap(span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
    for _ in range(max(span1[0], span2[0]), min(span1[-1], span2[-1])):
        return True
    return False

fn annualized_roi(duration: u64, roi: f64) -> f64 {
    let n = duration as f64 / YEAR_MS;
    if n == 0.0 {
        0.0
    } else {
        (1.0 + roi).powf(1.0 / n) - 1.0
    }
}
