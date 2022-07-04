from collections import deque
from typing import Any, NamedTuple

import pytest

from juno import inspect


class BasicNamedTuple(NamedTuple):
    value: int


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        (list, False),
        (list[int], False),
        (BasicNamedTuple, True),
        (BasicNamedTuple(value=1), True),
    ],
)
def test_isnamedtuple(input_, expected_output) -> None:
    assert inspect.isnamedtuple(input_) == expected_output


class Foo:
    pass


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        (deque, "collections::deque"),
        (Foo, "tests.test_inspect::Foo"),
    ],
)
def test_get_fully_qualified_name(input_: type[Any], expected_output: str) -> None:
    assert inspect.get_fully_qualified_name(input_) == expected_output


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        ("collections::deque", deque),
        ("tests.test_inspect::Foo", Foo),
    ],
)
def test_get_type_by_fully_qualified_name(input_: str, expected_output: type[Any]) -> None:
    assert inspect.get_type_by_fully_qualified_name("collections::deque") is deque


# Function local types not supported!
# def test_get_function_local_type_by_fully_qualified_named() -> None:
#     class Local:
#         pass

#     name = inspect.get_fully_qualified_name(Local)
#     assert inspect.get_type_by_fully_qualified_name(name) is Local
