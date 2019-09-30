from decimal import Decimal

import pytest

import juno.json as json


class Complex:
    def __init__(self, value: Decimal):
        self.value = value


@pytest.mark.parametrize('input,expected_output', [
    (Decimal('0.1'), '0.1'),
    (Complex(Decimal('0.1')), '{"value": 0.1}'),
    ({'value': Decimal('0.1')}, '{"value": 0.1}'),
    ([Decimal('0.1')], '[0.1]'),
])
def test_dumps(input, expected_output):
    assert json.dumps(input) == expected_output


@pytest.mark.parametrize('input,expected_output', [
    ('0.1', Decimal('0.1')),
    ('{"value": "0.1"}', {'value': '0.1'}),
    ('["0.1"]', ['0.1']),
])
def test_loads(input, expected_output):
    assert json.loads(input) == expected_output
