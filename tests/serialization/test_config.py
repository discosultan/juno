from decimal import Decimal
from enum import IntEnum
from typing import Any, Literal, NamedTuple, Optional, Union

from juno import Interval, Timestamp, serialization
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
    list_of_intervals: list[Interval]
    dict_of_intervals: dict[Interval, Interval]
    enum: SomeEnum
    union1: Union[str, int]
    union2: Union[str, int]
    literal: Literal["foo"]
    optional_union: Optional[Union[str, int]]


def test_deserialize_serialize() -> None:
    input_: dict[str, Any] = {
        "name": "bar",
        "timestamp": "2000-01-01T00:00:00+00:00",
        "interval": "1h",
        "optional_interval": "2h",
        "missing_optional_interval": None,
        "decimal": Decimal("1.5"),
        "list_of_intervals": ["1h", "2h"],
        "dict_of_intervals": {"1h": "2h"},
        "enum": "key",
        "union1": "foo",
        "union2": 1,
        "literal": "foo",
        "optional_union": "foo",
    }
    expected_output: Union[dict[str, Any], Foo] = Foo(
        name="bar",
        timestamp=946_684_800_000,
        interval=HOUR_MS,
        optional_interval=2 * HOUR_MS,
        missing_optional_interval=None,
        decimal=Decimal("1.5"),
        list_of_intervals=[HOUR_MS, 2 * HOUR_MS],
        dict_of_intervals={HOUR_MS: 2 * HOUR_MS},
        enum=SomeEnum.KEY,
        union1="foo",
        union2=1,
        literal="foo",
        optional_union="foo",
    )

    output = serialization.config.deserialize(input_, Foo)
    assert output == expected_output

    expected_output = input_
    input_ = output

    output = serialization.config.serialize(input_, Foo)
    assert output == expected_output


class Bar(NamedTuple):
    value1: int
    value2: int = 2


def test_deserialize_with_defaults() -> None:
    input_ = {"value1": 1}

    output = serialization.config.deserialize(input_, Bar)

    assert output == Bar(value1=1, value2=2)
