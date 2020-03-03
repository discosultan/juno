import sys
from decimal import Decimal
from enum import IntEnum
from typing import Any, Dict, List, NamedTuple, Optional, Union

from juno import Interval, Timestamp, config
from juno.time import HOUR_MS


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


def test_from_config_to_config() -> None:
    input_: Dict[str, Any] = {
        'name': 'bar',
        'timestamp': '2000-01-01 00:00:00+00:00',
        'interval': '1h',
        'optional_interval': '2h',
        'missing_optional_interval': None,
        'decimal': Decimal('1.5'),
        'list_of_intervals': ['1h', '2h'],
        'dict_of_intervals': {'1h': '2h'},
        'enum': 'key'
    }
    expected_output: Union[Dict[str, Any], Foo] = Foo(
        name='bar',
        timestamp=946_684_800_000,
        interval=HOUR_MS,
        optional_interval=2 * HOUR_MS,
        missing_optional_interval=None,
        decimal=Decimal('1.5'),
        list_of_intervals=[HOUR_MS, 2 * HOUR_MS],
        dict_of_intervals={HOUR_MS: 2 * HOUR_MS},
        enum=SomeEnum.KEY
    )

    output = config.from_config(input_, Foo)
    assert output == expected_output

    expected_output = input_
    input_ = output

    output = config.to_config(input_, Foo)
    assert output == expected_output


class Bar(NamedTuple):
    value: Interval


def test_init_module_instance() -> None:
    input_ = {
        'type': Bar.__name__.lower(),
        'value': '1h',
    }

    output = config.init_module_instance(sys.modules[__name__], input_)

    assert isinstance(output, Bar)
    assert output.value == HOUR_MS


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
