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


@pytest.mark.parametrize('size,min_size,max_size,size_step,expected_output', [
    (Decimal('0.1'), Decimal('0.2'), Decimal('0.3'), Decimal('0.1'), Decimal('0.0')),  # min
    (Decimal('0.4'), Decimal('0.2'), Decimal('0.3'), Decimal('0.1'), Decimal('0.3')),  # max
    (Decimal('0.25'), Decimal('0.2'), Decimal('0.3'), Decimal('0.1'), Decimal('0.2')),  # step
    (Decimal('1412.10939049659'), Decimal('0.00100000'), Decimal('100000.00000000'),
     Decimal('0.00100000'), Decimal('1412.109'))  # rounding down to step
])
def test_adjust_size(size, min_size, max_size, size_step, expected_output):
    output = math.adjust_size(size, min_size, max_size, size_step)
    assert output == expected_output


@pytest.mark.parametrize('price,min_price,max_price,price_step,expected_output', [
    (Decimal('0.000005540'), Decimal('1E-8'), Decimal('100000.00000000'), Decimal('1E-8'),
     Decimal('0.00000554'))
])
def test_adjust_price(price, min_price, max_price, price_step, expected_output):
    output = math.adjust_price(price, min_price, max_price, price_step)
    assert output == expected_output
