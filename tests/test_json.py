from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NamedTuple

import pytest

from juno import json


@dataclass
class Public:
    value: Any


@dataclass
class Private:
    _value: Any


class MyNamedTuple(NamedTuple):
    value: Decimal


@pytest.mark.parametrize(
    'input_,expected_output', [
        (Decimal('0.1'), '0.1'),
        (Public(Public(Decimal('0.1'))), '{"value": {"value": 0.1}}'),
        ({
            'value': Decimal('0.1')
        }, '{"value": 0.1}'),
        ([Decimal('0.1')], '[0.1]'),
        (0, '0'),
        (MyNamedTuple(value=Decimal('1.0')), '[1.0]'),
        (Decimal('Infinity'), 'Infinity'),
        (Decimal('-Infinity'), '-Infinity'),
        ('foo', '"foo"'),
        (deque([1, 2, 3]), '[1, 2, 3]'),
        ({
            'value': deque([1, 2, 3])
        }, '{"value": [1, 2, 3]}')
    ]
)
def test_dumps(input_, expected_output) -> None:
    assert json.dumps(input_, use_decimal=True) == expected_output


def test_dumps_skip_private() -> None:
    assert json.dumps(Private(1), skip_private=False) == '{"_value": 1}'
    assert json.dumps(Private(1), skip_private=True) == '{}'


def test_dumps_complicated() -> None:
    input_ = {
        'foo': Decimal('0.1'),
        'bar': 'hello',
        'baz': 1,
        'qux': [1],
        'quux': {
            'corge': 1
        },
    }
    expected_output = '{"foo": 0.1, "bar": "hello", "baz": 1, "qux": [1], "quux": {"corge": 1}}'
    assert json.dumps(input_, use_decimal=True) == expected_output


@pytest.mark.parametrize(
    'input_,expected_output', [
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
def test_loads(input_, expected_output) -> None:
    res = json.loads(input_, use_decimal=True)
    assert type(res) == type(expected_output)
    assert res == expected_output
