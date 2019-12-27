import sys
from decimal import Decimal
from typing import Dict, List, NamedTuple

from juno import Interval, Timestamp, config


class Foo(NamedTuple):
    name: str
    timestamp: Timestamp
    interval: Interval
    decimal: Decimal
    list_of_intervals: List[Interval]
    dict_of_intervals: Dict[Interval, Interval]


def test_init_module_instance():
    input = {
        'type': 'foo',
        'name': 'bar',
        'timestamp': '2000-01-01T00:00:00+00:00',
        'interval': '1h',
        'decimal': Decimal('1.5'),
        'list_of_intervals': ['1h', '2h'],
        'dict_of_intervals': {'1h': '2h'}
    }

    output = config.init_module_instance(sys.modules[__name__], input)

    assert output.name == 'bar'
    assert output.timestamp == 946_684_800_000
    assert output.interval == 3_600_000
    assert output.decimal == Decimal('1.5')
    assert output.list_of_intervals == [3_600_000, 7_200_000]
    assert output.dict_of_intervals.get(3_600_000) == 7_200_000


def test_load_from_env():
    input = {
        'JUNO__FOO__BAR': 'a',
        'JUNO__FOO__BAZ': 'b',
        'JUNO__QUX__0': 'c',
        'JUNO__QUX__1': 'd',
        'JUNO__QUUX__0__CORGE': 'e',
    }
    expected_output = {
        'foo': {
            'bar': 'a',
            'baz': 'b',
        },
        'qux': ['c', 'd'],
        'quux': [{
            'corge': 'e'
        }],
    }
    output = config.config_from_env(input)
    assert output == expected_output


def test_list_names():
    input = {
        'foo': {
            'bar': 'a'
        },
        'bars': ['b', 'c'],
        'baz': 'd',
        'qux': [{
            'bar': 'e'
        }],
    }
    expected_output = {'a', 'b', 'c', 'e'}
    output = config.list_names(input, 'bar')
    assert output == expected_output
