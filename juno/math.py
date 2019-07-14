import math
from decimal import Decimal
from random import Random
from typing import Callable, Tuple, TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


# TODO: Decimal?
def random_int_pair(amin: int, amax: int, op: Callable[[int, int], bool], bmin: int, bmax: int):
    def inner(random: Random):
        def inner2() -> Tuple[int, int]:
            while True:
                a = random.randint(amin, amax)
                b = random.randint(bmin, bmax)
                if op(a, b):
                    break
            return a, b

    return inner


def random_uniform(min_: float, max_: float):
    def inner(random: Random):
        def inner2() -> float:
            return random.uniform(min_, max_)

    return inner


def random_int(min_: int, max_: int):
    def inner(random: Random):
        def inner2() -> int:
            return random.randint(min_, max_)

    return inner
