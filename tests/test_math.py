from decimal import Decimal

import pytest

from juno import math


@pytest.mark.parametrize('value,multiple,expected_output', [
    (1, 5, 5),
    (5, 5, 5),
    (6, 5, 10),
    (Decimal('0.99'), Decimal('0.1'), Decimal('1.0')),
    (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
    (Decimal('1.01'), Decimal('0.1'), Decimal('1.1'))
])
def test_ceil_multiple(value, multiple, expected_output):
    output = math.ceil_multiple(value, multiple)
    assert output == expected_output


@pytest.mark.parametrize('value,multiple,expected_output', [
    (1, 5, 0),
    (5, 5, 5),
    (6, 5, 5),
    (Decimal('0.99'), Decimal('0.1'), Decimal('0.9')),
    (Decimal('1.00'), Decimal('0.1'), Decimal('1.0')),
    (Decimal('1.01'), Decimal('0.1'), Decimal('1.0'))
])
def test_floor_multiple(value, multiple, expected_output):
    output = math.floor_multiple(value, multiple)
    assert output == expected_output
