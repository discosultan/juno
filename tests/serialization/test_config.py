from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import Literal, NamedTuple, Optional, Tuple, TypedDict, Union

import pytest

from juno import Interval, Interval_, Timestamp, serialization


class BasicEnum(IntEnum):
    KEY = 1


class BasicNamedTuple(NamedTuple):
    value: Interval


class BasicTypedDict(TypedDict):
    value: Interval


@dataclass
class BasicDataClass:
    value: Interval


@pytest.mark.parametrize(
    "obj,type_,expected_output",
    [
        ("bar", str, "bar"),
        ("2020-01-01T00:00:00+00:00", Timestamp, 1577836800000),
        ("1d", Interval, Interval_.DAY),
        ("2h", Optional[Interval], 2 * Interval_.HOUR),
        (None, Optional[Interval], None),
        (Decimal("1.5"), Decimal, Decimal("1.5")),
        (["1h", "2h"], list[Interval], [Interval_.HOUR, 2 * Interval_.HOUR]),
        ({"1h": "2h"}, dict[Interval, Interval], {Interval_.HOUR: 2 * Interval_.HOUR}),
        ("key", BasicEnum, BasicEnum.KEY),
        ("foo", Union[str, int], "foo"),
        (1, Union[str, int], 1),
        ("foo", Literal["foo"], "foo"),
        ("foo", Optional[Union[str, int]], "foo"),
        (["a", 1], Tuple[str, int], ("a", 1)),
        (["1h"], BasicNamedTuple, BasicNamedTuple(value=Interval_.HOUR)),
        ({"value": "1h"}, BasicTypedDict, BasicTypedDict(value=Interval_.HOUR)),
        ({"value": "1h"}, BasicDataClass, BasicDataClass(value=Interval_.HOUR)),
    ],
)
def test_deserialize(obj, type_, expected_output) -> None:
    assert serialization.config.deserialize(obj, type_) == expected_output


@pytest.mark.parametrize(
    "obj,type_,expected_output",
    [
        ("bar", str, "bar"),
        (1577836800000, Timestamp, "2020-01-01T00:00:00+00:00"),
        (Interval_.DAY, Interval, "1d"),
        (2 * Interval_.HOUR, Optional[Interval], "2h"),
        (None, Optional[Interval], None),
        (Decimal("1.5"), Decimal, Decimal("1.5")),
        ([Interval_.HOUR, 2 * Interval_.HOUR], list[Interval], ["1h", "2h"]),
        ({Interval_.HOUR: 2 * Interval_.HOUR}, dict[Interval, Interval], {"1h": "2h"}),
        (BasicEnum.KEY, BasicEnum, "key"),
        ("foo", Union[str, int], "foo"),
        (1, Union[str, int], 1),
        ("foo", Literal["foo"], "foo"),
        ("foo", Optional[Union[str, int]], "foo"),
        (("a", 1), Tuple[str, int], ["a", 1]),
        (BasicNamedTuple(value=Interval_.HOUR), BasicNamedTuple, ["1h"]),
        (BasicTypedDict(value=Interval_.HOUR), BasicTypedDict, {"value": "1h"}),
        (BasicDataClass(value=Interval_.HOUR), BasicDataClass, {"value": "1h"}),
    ],
)
def test_serialize(obj, type_, expected_output) -> None:
    assert serialization.config.serialize(obj, type_) == expected_output


class Bar(NamedTuple):
    value1: int
    value2: int = 2


def test_deserialize_with_defaults() -> None:
    # input_ = {"value1": 1}
    input_ = [1]

    output = serialization.config.deserialize(input_, Bar)

    assert output == Bar(value1=1, value2=2)
