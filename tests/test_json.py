from decimal import Decimal

import pytest

from juno import json


@pytest.mark.parametrize(
    'input_,expected_output', [
        (Decimal('0.1'), '0.1'),
        ({
            'value': Decimal('0.1')
        }, '{"value": 0.1}'),
        ([Decimal('0.1')], '[0.1]'),
        (0, '0'),
        (Decimal('Infinity'), 'Infinity'),
        (Decimal('-Infinity'), '-Infinity'),
        ('foo', '"foo"'),
    ]
)
def test_dumps(input_, expected_output) -> None:
    assert json.dumps(input_) == expected_output


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
    assert json.dumps(input_) == expected_output


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
    res = json.loads(input_)
    assert type(res) == type(expected_output)
    assert res == expected_output
