import math
from abc import ABC, abstractmethod
from decimal import Decimal
from random import Random
from typing import Any, Callable, List, TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


class Randomizer(ABC):

    validate: Callable[..., bool] = abstractmethod(lambda: True)

    @abstractmethod
    def random(self, random: Random) -> Any:
        pass


class Uniform(Randomizer):
    def __init__(self, min_: Decimal, max_: Decimal) -> None:
        self.min = min_
        self.max = max_

        _min_sign, _min_digits, min_exponent = min_.as_tuple()
        _max_sign, _max_digits, max_exponent = max_.as_tuple()

        if min_exponent != max_exponent:
            raise ValueError('Min and max must have same number of specified decimal places.')

        self.factor = 10**abs(min_exponent)

        self.min_int = int(min_ * self.factor)
        self.max_int = int(max_ * self.factor)

    def validate(self, value: Decimal) -> bool:
        return value >= self.min and value <= self.max

    def random(self, random: Random) -> Decimal:
        # Approach 1.
        # https://stackoverflow.com/a/439169/1466456
        # return Decimal(str(random.uniform(float(self.min), float(self.max))))

        # Approach 2.
        # https://stackoverflow.com/a/40972516/1466456
        return Decimal(random.randrange(self.min_int, self.max_int)) / self.factor


class Int(Randomizer):
    def __init__(self, min_: int, max_: int) -> None:
        self.min = min_
        self.max = max_

    def validate(self, value: int) -> bool:
        return value >= self.min and value < self.max

    def random(self, random: Random) -> int:
        return random.randrange(self.min, self.max)


class Choice(Randomizer):
    def __init__(self, choices: List[Any]) -> None:
        self.choices = choices

    def validate(self, value: Any) -> bool:
        return value in self.choices

    def random(self, random: Random) -> Any:
        return random.choice(self.choices)
