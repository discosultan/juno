import pytest

from juno import math


@pytest.mark.parametrize('value,multiple,expected_output', [
    (1, 5, 5),
    (5, 5, 5),
    (6, 5, 10)
])
def test_ceil_multiple(value, multiple, expected_output):
    output = math.ceil_multiple(value, multiple)
    assert output == expected_output


@pytest.mark.parametrize('value,multiple,expected_output', [
    (1, 5, 0),
    (5, 5, 5),
    (6, 5, 5)
])
def test_floor_multiple(value, multiple, expected_output):
    output = math.floor_multiple(value, multiple)
    assert output == expected_output
