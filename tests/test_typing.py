from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import (  # type: ignore
    Deque, Dict, Generic, List, NamedTuple, Optional, Tuple, TypeVar, _GenericAlias
)

import pytest

from juno import typing

T1 = TypeVar('T1')
T2 = TypeVar('T2')
T3 = TypeVar('T3')


def foo(a: int) -> int:
    return a


class Bar(NamedTuple):
    value1: int
    value2: Optional[int]


@dataclass
class Baz:
    value1: int
    value2: Optional[int]


class Qux(IntEnum):
    VALUE = 1


@dataclass
class Quux(Generic[T1]):
    value: T1


IntAlias = _GenericAlias(int, (), name='IntAlias')


@dataclass
class Corge(Generic[T1, T2, T3]):
    value1: T1
    value2: Optional[T2]
    value3: Quux[T3]
    value4: Quux[int]
    value5: IntAlias  # type: ignore


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


@pytest.mark.parametrize('obj,type_,expected_output', [
    ([1, 2], Bar, Bar(1, 2)),
    ([1, [2, 3]], Tuple[int, Bar], [1, Bar(2, 3)]),
    ([1, 2], List[int], [1, 2]),
    ({'value1': 1, 'value2': 2}, Baz, Baz(value1=1, value2=2)),
    ([1.0, 2.0], Deque[Decimal], deque([Decimal('1.0'), Decimal('2.0')])),
    (1, Qux, Qux.VALUE),
    ({'value': 1}, Quux[int], Quux(value=1)),
    (
        {'value1': 1, 'value2': 2, 'value3': {'value': 3}, 'value4': {'value': 4}, 'value5': 5},
        Corge[int, int, int],
        Corge(value1=1, value2=2, value3=Quux(value=3), value4=Quux(value=4), value5=5),
    ),
])
def test_raw_to_type(obj, type_, expected_output) -> None:
    assert typing.raw_to_type(obj, type_) == expected_output


@pytest.mark.parametrize('input_,type_,expected_output', [
    (Bar(1, 2), Bar, True),
    ((1, ), Bar, False),
    (1, int, True),
    ('a', int, False),
    ({'a': Bar(1, 2)}, Dict[str, Bar], True),
    ({'a': 1, 'b': 'x'}, Dict[str, int], False),
    ({'value': 1}, Bar, False),
    ([Bar(1, 2)], List[Bar], True),
    ([1, 'x'], List[int], False),
    ((1, 'x'), Tuple[int, str], True),
    (Baz(1, 2), Baz, True),
    (1, Optional[int], True),
    (deque([Decimal('1.0')]), Deque[Decimal], True),
    (deque([1]), Deque[str], False),
])
def test_types_match(input_, type_, expected_output) -> None:
    assert typing.types_match(input_, type_) == expected_output
