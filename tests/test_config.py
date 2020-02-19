import sys
from decimal import Decimal
from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional

from juno import Interval, Timestamp, config


class SomeEnum(IntEnum):
    KEY = 1


class Foo(NamedTuple):
    name: str
    timestamp: Timestamp
    interval: Interval
    optional_interval: Optional[Interval]
    missing_optional_interval: Optional[Interval]
    decimal: Decimal
    list_of_intervals: List[Interval]
    dict_of_intervals: Dict[Interval, Interval]
    enum: SomeEnum


def test_init_module_instance() -> None:
    input_ = {
        'type': 'foo',
        'name': 'bar',
        'timestamp': '2000-01-01T00:00:00+00:00',
        'interval': '1h',
        'optional_interval': '2h',
        'missing_optional_interval': None,
        'decimal': Decimal('1.5'),
        'list_of_intervals': ['1h', '2h'],
        'dict_of_intervals': {'1h': '2h'},
        'enum': 'key'
    }

    output = config.init_module_instance(sys.modules[__name__], input_)

    assert output.name == 'bar'
    assert output.timestamp == 946_684_800_000
    assert output.interval == 3_600_000
    assert output.optional_interval == 7_200_000
    assert output.missing_optional_interval is None
    assert output.decimal == Decimal('1.5')
    assert output.list_of_intervals == [3_600_000, 7_200_000]
    assert output.dict_of_intervals.get(3_600_000) == 7_200_000
    assert output.enum == SomeEnum.KEY


def test_load_from_env() -> None:
    input_ = {
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
    output = config.from_env(input_)
    assert output == expected_output


def test_list_names() -> None:
    input_ = {
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
    output = config.list_names(input_, 'bar')
    assert output == expected_output
