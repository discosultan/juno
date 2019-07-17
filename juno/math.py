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

    validate: Callable[..., bool] = abstractmethod(lambda: True)

    @abstractmethod
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
        value = a, b
        print(value)
        return value


# TODO: Decimal?
class Uniform(Constraint):
    def __init__(self, min_: float, max_: float) -> None:
        self.min = min_
        self.max = max_

    def validate(self, value: float) -> bool:
        return value >= self.min and value <= self.max

    def random(self, random: Random) -> float:
        value = random.uniform(self.min, self.max)
        print(value)
        return value


class Int(Constraint):
    def __init__(self, min_: int, max_: int) -> None:
        self.min = min_
        self.max = max_

    def validate(self, value: int) -> bool:
        return value >= self.min and value < self.max

    def random(self, random: Random) -> int:
        value = random.randint(self.min, self.max)
        print(value)
        return value
