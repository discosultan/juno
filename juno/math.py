import math
from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal
from random import Random
from typing import Any, Callable, Iterable, List, Tuple, TypeVar

TNum = TypeVar('TNum', int, Decimal)


def ceil_multiple(value: TNum, multiple: TNum) -> TNum:
    return int(math.ceil(value / multiple)) * multiple


def floor_multiple(value: TNum, multiple: TNum) -> TNum:
    return value - (value % multiple)


def round_half_up(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_HALF_UP)


def minmax(values: Iterable[Decimal]) -> Tuple[Decimal, Decimal]:
    min_ = Decimal('Inf')
    max_ = Decimal('-Inf')
    for value in values:
        min_ = min(min_, value)
        max_ = max(max_, value)
    return min_, max_


class Constraint(ABC):

    validate: Callable[..., bool] = abstractmethod(lambda: True)

    @abstractmethod
    def random(self, random: Random) -> Any:
        pass


class Constant(Constraint):
    def __init__(self, value: Any) -> None:
        self._value = value

    def validate(self, value: Any) -> bool:
        return value == self._value

    def random(self, random: Random) -> Any:
        return self._value


class Choice(Constraint):
    def __init__(self, choices: List[Any]) -> None:
        self._choices = choices

    def validate(self, value: Any) -> bool:
        return value in self._choices

    def random(self, random: Random) -> Any:
        return random.choice(self._choices)


class ConstraintChoice(Constraint):
    def __init__(self, choices: List[Constraint]) -> None:
        self._choices = choices

    def validate(self, value: Any) -> bool:
        return any(choice.validate(value) for choice in self._choices)

    def random(self, random: Random) -> Any:
        return random.choice(self._choices).random(random)


class Uniform(Constraint):
    def __init__(self, min_: Decimal, max_: Decimal) -> None:
        self._min = min_
        self._max = max_

        _min_sign, _min_digits, min_exponent = min_.as_tuple()
        _max_sign, _max_digits, max_exponent = max_.as_tuple()

        if min_exponent != max_exponent:
            raise ValueError('Min and max must have same number of specified decimal places.')

        self._factor = 10**abs(min_exponent)

        self._min_int = int(min_ * self._factor)
        self._max_int = int(max_ * self._factor)

    def validate(self, value: Decimal) -> bool:
        return value >= self._min and value <= self._max

    def random(self, random: Random) -> Decimal:
        # Approach 1.
        # https://stackoverflow.com/a/439169/1466456
        # return Decimal(str(random.uniform(float(self._min), float(self._max))))

        # Approach 2.
        # https://stackoverflow.com/a/40972516/1466456
        return Decimal(random.randrange(self._min_int, self._max_int)) / self._factor


class Int(Constraint):
    def __init__(self, min_: int, max_: int) -> None:
        self._min = min_
        self._max = max_

    def validate(self, value: int) -> bool:
        return value >= self._min and value < self._max

    def random(self, random: Random) -> int:
        return random.randrange(self._min, self._max)


class Pair(Constraint):
    def __init__(self, a: Constraint, op: Callable[[Any, Any], bool], b: Constraint) -> None:
        self._a = a
        self._op = op
        self._b = b

    def validate(self, a: Any, b: Any) -> bool:
        return self._a.validate(a) and self._b.validate(b) and self._op(a, b)

    def random(self, random: Random) -> Tuple[int, int]:
        while True:
            a = self._a.random(random)
            b = self._b.random(random)
            if self.validate(a, b):
                break
        return a, b
