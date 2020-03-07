from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import Deque, Dict, Generic, List, NamedTuple, Optional, Tuple, TypeVar

import pytest

from juno import typing

T = TypeVar('T')


def foo(a: int) -> int:
    return a


class Bar(NamedTuple):
    value: int


@dataclass
class Baz(Generic[T]):
    value1: str
    value2: T
    value3: Optional[float]


class Qux(IntEnum):
    VALUE = 1


def test_get_input_type_hints() -> None:
    assert typing.get_input_type_hints(foo) == {'a': int}


@pytest.mark.parametrize('input_,expected_output', [
    (list, 'list'),
    (List[int], 'typing.List[int]'),
    (Bar, 'Bar'),
    # (Optional[int], 'typing.Optional[int]'),  # 'typing.Union[int, None]'
])
def test_get_name(input_, expected_output) -> None:
    assert typing.get_name(input_) == expected_output


@pytest.mark.parametrize('input_,expected_output', [
    (list, False),
    (List[int], False),
    (Bar, True),
])
def test_isnamedtuple(input_, expected_output) -> None:
    assert typing.isnamedtuple(input_) == expected_output


@pytest.mark.parametrize('input_,expected_output', [
    (int, False),
    (Optional[int], True),
])
def test_isoptional(input_, expected_output) -> None:
    assert typing.isoptional(input_) == expected_output


@pytest.mark.parametrize('obj,type_,expected_output', [
    ([1], Bar, Bar(value=1)),
    ([1, [2]], Tuple[int, Bar], [1, Bar(value=2)]),
    ([1, 2], List[int], [1, 2]),
    ({'value1': 'a', 'value2': 1, 'value3': 2.0}, Baz[int], Baz('a', 1, 2.0)),
    ([1.0, 2.0], Deque[Decimal], deque([Decimal('1.0'), Decimal('2.0')])),
    (1, Qux, Qux.VALUE),
])
def test_raw_to_type(obj, type_, expected_output) -> None:
    assert typing.raw_to_type(obj, type_) == expected_output


@pytest.mark.parametrize('input_,type_,expected_output', [
    (Bar(1), Bar, True),
    ((1, ), Bar, False),
    (1, int, True),
    ('a', int, False),
    ({'a': Bar(1)}, Dict[str, Bar], True),
    ({'a': 1, 'b': 'x'}, Dict[str, int], False),
    ({'value': 1}, Bar, False),
    ([Bar(1)], List[Bar], True),
    ([1, 'x'], List[int], False),
    ((1, 'x'), Tuple[int, str], True),
    (Baz('a', 1, 2.0), Baz[int], True),
    (1, Optional[int], True),
    (deque([Decimal('1.0')]), Deque[Decimal], True),
    (deque([1]), Deque[str], False),
])
def test_types_match(input_, type_, expected_output) -> None:
    assert typing.types_match(input_, type_) == expected_output
