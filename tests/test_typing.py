# Mypy requires us to use `Tuple` instead of `tuple` when passing it around as an object.

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Optional, Tuple, Union

import pytest

from juno import typing


def foo(a: int) -> int:
    return a


class BasicNamedTuple(NamedTuple):
    value1: int
    value2: Optional[int] = 2


@dataclass
class BasicDataClass:
    value1: int
    value2: Optional[int]


def test_get_input_type_hints() -> None:
    assert typing.get_input_type_hints(foo) == {"a": int}


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        (list, "list"),
        (list[int], "list[int]"),
        (BasicNamedTuple, "BasicNamedTuple"),
        # (Optional[int], 'typing.Optional[int]'),  # 'typing.Union[int, None]'
    ],
)
def test_get_name(input_: type[Any], expected_output: str) -> None:
    assert typing.get_name(input_) == expected_output


@pytest.mark.parametrize(
    "input_,type_,expected_output",
    [
        (BasicNamedTuple(1, 2), BasicNamedTuple, True),
        ((1,), BasicNamedTuple, False),
        (1, int, True),
        ("a", int, False),
        ("value", str, True),
        ({"a": BasicNamedTuple(1, 2)}, dict[str, BasicNamedTuple], True),
        ({"a": 1, "b": "x"}, dict[str, int], False),
        ({"value": 1}, BasicNamedTuple, False),
        ([BasicNamedTuple(1, 2)], list[BasicNamedTuple], True),
        ([1, "x"], list[int], False),
        ((1, "x"), Tuple[int, str], True),
        (BasicDataClass(1, 2), BasicDataClass, True),
        (1, Optional[int], True),
        (None, Optional[int], True),
        (deque([Decimal("1.0")]), deque[Decimal], True),
        (deque([1]), deque[str], False),
        (1, Literal[1], True),
        (1, Literal[2], False),
        (1, Literal[1, 2], True),
        (1, Literal[2, 3], False),
        ("bar", Union[Literal["foo"], Literal["bar"]], True),
    ],
)
def test_types_match(input_: Any, type_: type[Any], expected_output: bool) -> None:
    assert typing.types_match(input_, type_) == expected_output
