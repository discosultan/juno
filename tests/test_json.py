from decimal import Decimal
from typing import NamedTuple

import pytest

from juno import json


class Complex:
    def __init__(self, value):
        self.value = value


class MyNamedTuple(NamedTuple):
    value: Decimal


@pytest.mark.parametrize(
    'input,expected_output', [
        (Decimal('0.1'), '0.1'),
        (Complex(Complex(Decimal('0.1'))), '{"value": {"value": 0.1}}'),
        ({
            'value': Decimal('0.1')
        }, '{"value": 0.1}'),
        ([Decimal('0.1')], '[0.1]'),
        (0, '0'),
        (MyNamedTuple(value=Decimal('1.0')), '[1.0]'),
        (Decimal('Infinity'), 'Infinity'),
        (Decimal('-Infinity'), '-Infinity'),
        ('foo', '"foo"'),
    ]
)
def test_dumps(input, expected_output) -> None:
    assert json.dumps(input, use_decimal=True) == expected_output


def test_dumps_complicated() -> None:
    input = {
        'foo': Decimal('0.1'),
        'bar': 'hello',
        'baz': 1,
        'qux': [1],
        'quux': {
            'corge': 1
        },
    }
    expected_output = '{"foo": 0.1, "bar": "hello", "baz": 1, "qux": [1], "quux": {"corge": 1}}'
    assert json.dumps(input, use_decimal=True) == expected_output


@pytest.mark.parametrize(
    'input,expected_output', [
        ('0.1', Decimal('0.1')),
        ('{"value": 0.1}', {
            'value': Decimal('0.1')
        }),
        ('[0.1]', [Decimal('0.1')]),
        ('0', 0),
        ('Infinity', Decimal('Infinity')),
        ('-Infinity', Decimal('-Infinity')),
        ('"foo"', 'foo'),
    ]
)
def test_loads(input, expected_output) -> None:
    res = json.loads(input, use_decimal=True)
    assert type(res) == type(expected_output)
    assert res == expected_output
