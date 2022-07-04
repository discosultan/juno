from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, IntEnum
from typing import (  # type: ignore
    Any,
    Generic,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    TypeVar,
    Union,
    _GenericAlias,
)

import pytest

from juno import serialization

T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


class BasicNamedTuple(NamedTuple):
    value1: int
    value2: Optional[int] = 2


@dataclass
class BasicDataClass:
    value1: int
    value2: Optional[int]


class BasicEnum(IntEnum):
    VALUE = 1


class StringEnum(Enum):
    VALUE = "foo"


@dataclass
class GenericDataClass(Generic[T1]):
    value: T1


@dataclass(frozen=True)
class FrozenDataClass:
    value: int


@dataclass
class FieldDataClass:
    value: int = field(default_factory=int)


IntAlias = _GenericAlias(int, (), name="IntAlias")


@dataclass
class CombinedDataClass(Generic[T1, T2, T3]):
    value1: T1
    value2: T1
    value3: Optional[T2]
    value4: GenericDataClass[T3]
    value5: GenericDataClass[int]
    value6: IntAlias  # type: ignore
    value7: Union[IntAlias, int]  # type: ignore
    value8: Union[int, BasicNamedTuple]
    value9: Optional[Union[int, BasicNamedTuple]]


@pytest.mark.parametrize(
    "obj,type_,expected_output",
    [
        ([1, 2], BasicNamedTuple, BasicNamedTuple(1, 2)),
        ([1], BasicNamedTuple, BasicNamedTuple(1, 2)),
        ([1, [2, 3]], Tuple[int, BasicNamedTuple], (1, BasicNamedTuple(2, 3))),
        ([1, 2], list[int], [1, 2]),
        ({"value1": 1, "value2": 2}, BasicDataClass, BasicDataClass(value1=1, value2=2)),
        ([1.0, 2.0], deque[Decimal], deque([Decimal("1.0"), Decimal("2.0")])),
        (1, BasicEnum, BasicEnum.VALUE),
        ("foo", StringEnum, StringEnum.VALUE),
        ({"value": 1}, GenericDataClass[int], GenericDataClass(value=1)),
        (
            {
                "value1": 1,
                "value2": 2,
                "value3": 3,
                "value4": {"value": 4},
                "value5": {"value": 5},
                "value6": 6,
                "value7": 7,
                "value8": [81, 82],
                "value9": [91, 92],
            },
            CombinedDataClass[int, int, int],
            CombinedDataClass(
                value1=1,
                value2=2,
                value3=3,
                value4=GenericDataClass(value=4),
                value5=GenericDataClass(value=5),
                value6=6,
                value7=7,
                value8=BasicNamedTuple(value1=81, value2=82),
                value9=BasicNamedTuple(value1=91, value2=92),
            ),
        ),
        (1, Optional[Union[int, str]], 1),
        (None, type(None), None),
        (None, Any, None),
        ({"value": 1}, FrozenDataClass, FrozenDataClass(value=1)),
        ({"value": 1}, FieldDataClass, FieldDataClass(value=1)),
        ([1, 2], Tuple[int, ...], (1, 2)),
        ("foo", Literal["foo"], "foo"),
    ],
)
def test_deserialize(obj, type_, expected_output) -> None:
    assert serialization.raw.deserialize(obj, type_) == expected_output


@pytest.mark.parametrize(
    "obj,expected_output",
    [
        (BasicEnum.VALUE, 1),
        (StringEnum.VALUE, "foo"),
    ],
)
def test_serialize(obj, expected_output) -> None:
    assert serialization.raw.serialize(obj) == expected_output
