import sys
from typing import NamedTuple

from juno import Interval, config
from juno.time import HOUR_MS


class Foo(NamedTuple):
    value: Interval


def test_init_module_instance() -> None:
    input_ = {
        "type": Foo.__name__.lower(),
        "value": "1h",
    }

    output = config.init_module_instance(sys.modules[__name__], input_)

    assert isinstance(output, Foo)
    assert output.value == HOUR_MS


def test_load_from_env() -> None:
    input_ = {
        "JUNO__FOO__BAR": "a",
        "JUNO__FOO__BAZ": "b",
        "JUNO__QUX__0": "c",
        "JUNO__QUX__1": "d",
        "JUNO__QUUX__0__CORGE": "e",
    }
    expected_output = {
        "foo": {
            "bar": "a",
            "baz": "b",
        },
        "qux": ["c", "d"],
        "quux": [{"corge": "e"}],
    }
    output = config.from_env(input_)
    assert output == expected_output


def test_list_names() -> None:
    input_ = {
        "foo": {"bar": "a"},
        "bars": ["b", "c"],
        "baz": "d",
        "qux": [{"bar": "e"}],
        "dummy_bar": "f",
        "dummy_bars": ["g"],
        "bar_baz": "h",  # Shouldn't be included.
    }
    expected_output = {"a", "b", "c", "e", "f", "g"}
    output = config.list_names(input_, "bar")
    assert output == expected_output
