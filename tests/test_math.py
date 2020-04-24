import operator
from decimal import Decimal
from random import Random
from typing import Tuple

import pytest

from juno import math


@pytest.mark.parametrize(
    'value,multiple,expected_output', [(1, 5, 5), (5, 5, 5), (6, 5, 10),
                                       (Decimal('0.99'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.01'), Decimal('0.1'), Decimal('1.1'))]
)
def test_ceil_multiple(value, multiple, expected_output) -> None:
    output = math.ceil_multiple(value, multiple)
    assert output == expected_output


@pytest.mark.parametrize(
    'value,multiple,expected_output', [(1, 5, 0), (5, 5, 5), (6, 5, 5),
                                       (Decimal('0.99'), Decimal('0.1'), Decimal('0.9')),
                                       (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.01'), Decimal('0.1'), Decimal('1.0'))]
)
def test_floor_multiple(value, multiple, expected_output) -> None:
    output = math.floor_multiple(value, multiple)
    assert output == expected_output


def test_round_half_up() -> None:
    assert math.round_half_up(Decimal('0.123'), 2) == Decimal('0.12')


def test_minmax() -> None:
    output = math.minmax([Decimal('2.0'), Decimal('1.0'), Decimal('3.0')])
    assert output == (Decimal('1.0'), Decimal('3.0'))


def test_split_by_ratios() -> None:
    output = math.split_by_ratios(
        Decimal('0.24690'),
        math.ratios(
            Decimal('0.12345'),
            [Decimal('0.10000'), Decimal('0.02340'), Decimal('0.00005')],
        ),
    )
    assert output == [Decimal('0.20000'), Decimal('0.04680'), Decimal('0.00010')]


@pytest.mark.parametrize('span1,span2,expected_output', [
    ((0, 2), (2, 4), False),
    ((0, 3), (2, 4), True),
])
def test_spans_overlap(
    span1: Tuple[int, int], span2: Tuple[int, int], expected_output: bool
) -> None:
    output = math.spans_overlap(span1, span2)
    assert output == expected_output


def test_constant_constraint() -> None:
    assert_constraint_chaos(math.Constant('foo'))


def test_choice_constraint() -> None:
    assert_constraint_chaos(math.Choice(['foo', 'bar']))


def test_constraint_choice_constraint() -> None:
    assert_constraint_chaos(math.ConstraintChoice([
        math.Constant(Decimal('0.0')),
        math.Uniform(Decimal('0.0001'), Decimal('0.9999')),
    ]))


def test_uniform_constraint() -> None:
    assert_constraint_chaos(math.Uniform(Decimal('-0.10'), Decimal('2.00')))


def test_int_constraint() -> None:
    assert_constraint_chaos(math.Int(-10, 10))


def test_int_pair_constraint() -> None:
    assert_constraint_chaos(math.Pair(math.Int(-10, 10), operator.lt, math.Int(5, 20)))


def assert_constraint_chaos(randomizer):
    random = Random()
    for _ in range(0, 1000):
        value = randomizer.random(random)
    if isinstance(value, tuple):
        assert randomizer.validate(*value)
    else:
        assert randomizer.validate(value)
