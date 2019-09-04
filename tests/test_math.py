import operator
from decimal import Decimal
from random import Random

import pytest

from juno import math


@pytest.mark.parametrize(
    'value,multiple,expected_output', [(1, 5, 5), (5, 5, 5), (6, 5, 10),
                                       (Decimal('0.99'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.01'), Decimal('0.1'), Decimal('1.1'))]
)
def test_ceil_multiple(value, multiple, expected_output):
    output = math.ceil_multiple(value, multiple)
    assert output == expected_output


@pytest.mark.parametrize(
    'value,multiple,expected_output', [(1, 5, 0), (5, 5, 5), (6, 5, 5),
                                       (Decimal('0.99'), Decimal('0.1'), Decimal('0.9')),
                                       (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
                                       (Decimal('1.01'), Decimal('0.1'), Decimal('1.0'))]
)
def test_floor_multiple(value, multiple, expected_output):
    output = math.floor_multiple(value, multiple)
    assert output == expected_output


@pytest.mark.manual
@pytest.mark.chaos
def test_uniform_randomizer():
    assert_randomizer_chaos(math.Uniform(Decimal('-0.10'), Decimal('2.00')))


@pytest.mark.manual
@pytest.mark.chaos
def test_int_randomizer():
    assert_randomizer_chaos(math.Int(-10, 10))


@pytest.mark.manual
@pytest.mark.chaos
def test_choice_randomizer():
    assert_randomizer_chaos(math.Choice(['foo', 'bar']))


def assert_randomizer_chaos(randomizer):
    random = Random()
    for i in range(0, 1000):
        value = randomizer.random(random)
    if isinstance(value, tuple):
        assert randomizer.validate(*value)
    else:
        assert randomizer.validate(value)
