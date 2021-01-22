from decimal import Decimal
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


def test_round_down() -> None:
    assert math.round_down(Decimal('0.004943799'), 8) == Decimal('0.00494379')


def test_minmax() -> None:
    output = math.minmax([Decimal('2.0'), Decimal('1.0'), Decimal('3.0')])
    assert output == (Decimal('1.0'), Decimal('3.0'))


@pytest.mark.parametrize('input_,parts,expected_output', [
    (
        Decimal('1.0001'),
        4,
        [Decimal('0.2500'), Decimal('0.2500'), Decimal('0.2500'), Decimal('0.2501')],
    ),
    (
        Decimal('1.0001'),
        1,
        [Decimal('1.0001')],
    ),
])
def test_split(input_: Decimal, parts: int, expected_output: list[Decimal]) -> None:
    output = math.split(input_, parts)
    assert output == expected_output


@pytest.mark.parametrize('span1,span2,expected_output', [
    ((0, 2), (2, 4), False),
    ((0, 3), (2, 4), True),
])
def test_spans_overlap(
    span1: Tuple[int, int], span2: Tuple[int, int], expected_output: bool
) -> None:
    output = math.spans_overlap(span1, span2)
    assert output == expected_output


def test_lerp() -> None:
    assert math.lerp(Decimal('-1.0'), Decimal('3.0'), Decimal('0.5')) == Decimal('1.0')
