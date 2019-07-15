import math
from abc import ABC, abstractmethod
from decimal import Decimal
from random import Random
from typing import Any, Callable, Tuple, TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


class Constraint(ABC):

    # @abstractmethod
    validate: Callable[..., bool] = lambda: True

    def random(self, random: Random) -> Any:
        pass


class IntPair(Constraint):
    def __init__(
        self, amin: int, amax: int, op: Callable[[int, int], bool], bmin: int, bmax: int
    ) -> None:
        self.amin = amin
        self.amax = amax
        self.op = op
        self.bmin = bmin
        self.bmax = bmax

    def validate(self, a: int, b: int) -> bool:
        return self.op(a, b)

    def random(self, random: Random) -> Tuple[int, int]:
        while True:
            a = random.randint(self.amin, self.amax)
            b = random.randint(self.bmin, self.bmax)
            if self.validate(a, b):
                break
        return a, b


class Uniform(Constraint):
    def __init__(self, min_: float, max_: float) -> None:
        self.min = min_
        self.max = max_

    def validate(self, value: float) -> bool:
        return value >= self.min and value < self.max

    def random(self, random: Random) -> float:
        return random.uniform(self.min, self.max)


class Int(Constraint):
    def __init__(self, min_: int, max_: int) -> None:
        self.min = min_
        self.max = max_

    def validate(self, value: int) -> bool:
        return value >= self.min and value < self.max

    def random(self, random: Random) -> int:
        return random.randint(self.min, self.max)


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
