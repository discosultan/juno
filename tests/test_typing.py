from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from typing import (  # type: ignore
    Any, Deque, Dict, Generic, List, NamedTuple, Optional, Tuple, TypeVar, Union, _GenericAlias
)

import pytest

from juno import typing

T1 = TypeVar('T1')
T2 = TypeVar('T2')
T3 = TypeVar('T3')


def foo(a: int) -> int:
    return a


class BasicNamedTuple(NamedTuple):
    value1: int
    value2: Optional[int] = 2


@dataclass
class BasicDataClass:
    value1: int
    value2: Optional[int]


class BasicEnum(IntEnum):
    VALUE = 1


@dataclass
class GenericDataClass(Generic[T1]):
    value: T1


@dataclass(frozen=True)
class FrozenDataClass:
    value: int


@dataclass
class FieldDataClass:
    value: int = field(default_factory=int)


IntAlias = _GenericAlias(int, (), name='IntAlias')


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


def test_get_input_type_hints() -> None:
    assert typing.get_input_type_hints(foo) == {'a': int}


@pytest.mark.parametrize('input_,expected_output', [
    (list, 'list'),
    (List[int], 'typing.List[int]'),
    (BasicNamedTuple, 'BasicNamedTuple'),
    # (Optional[int], 'typing.Optional[int]'),  # 'typing.Union[int, None]'
])
def test_get_name(input_, expected_output) -> None:
    assert typing.get_name(input_) == expected_output


@pytest.mark.parametrize('input_,expected_output', [
    (list, False),
    (List[int], False),
    (BasicNamedTuple, True),
    (BasicNamedTuple(value1=1), True),
])
def test_isnamedtuple(input_, expected_output) -> None:
    assert typing.isnamedtuple(input_) == expected_output


@pytest.mark.parametrize('obj,type_,expected_output', [
    ([1, 2], BasicNamedTuple, BasicNamedTuple(1, 2)),
    ([1], BasicNamedTuple, BasicNamedTuple(1, 2)),
    ([1, [2, 3]], Tuple[int, BasicNamedTuple], (1, BasicNamedTuple(2, 3))),
    ([1, 2], List[int], [1, 2]),
    ({'value1': 1, 'value2': 2}, BasicDataClass, BasicDataClass(value1=1, value2=2)),
    ([1.0, 2.0], Deque[Decimal], deque([Decimal('1.0'), Decimal('2.0')])),
    (1, BasicEnum, BasicEnum.VALUE),
    ({'value': 1}, GenericDataClass[int], GenericDataClass(value=1)),
    (
        {
            'value1': 1,
            'value2': 2,
            'value3': 3,
            'value4': {'value': 4},
            'value5': {'value': 5},
            'value6': 6,
            'value7': 7,
            'value8': [81, 82],
            'value9': [91, 92],
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
    ({'value': 1}, FrozenDataClass, FrozenDataClass(value=1)),
    ({'value': 1}, FieldDataClass, FieldDataClass(value=1)),
    ([1, 2], Tuple[int, ...], (1, 2)),
])
def test_raw_to_type(obj, type_, expected_output) -> None:
    assert typing.raw_to_type(obj, type_) == expected_output


@pytest.mark.parametrize('input_,type_,expected_output', [
    (BasicNamedTuple(1, 2), BasicNamedTuple, True),
    ((1, ), BasicNamedTuple, False),
    (1, int, True),
    ('a', int, False),
    ({'a': BasicNamedTuple(1, 2)}, Dict[str, BasicNamedTuple], True),
    ({'a': 1, 'b': 'x'}, Dict[str, int], False),
    ({'value': 1}, BasicNamedTuple, False),
    ([BasicNamedTuple(1, 2)], List[BasicNamedTuple], True),
    ([1, 'x'], List[int], False),
    ((1, 'x'), Tuple[int, str], True),
    (BasicDataClass(1, 2), BasicDataClass, True),
    (1, Optional[int], True),
    (deque([Decimal('1.0')]), Deque[Decimal], True),
    (deque([1]), Deque[str], False),
])
def test_types_match(input_, type_, expected_output) -> None:
    assert typing.types_match(input_, type_) == expected_output


@pytest.mark.parametrize('input_,expected_output', [
    (deque((1, 2, 3)), 'collections::deque'),
    (deque, 'collections::deque'),
])
def test_get_fully_qualified_name(input_: Any, expected_output: str) -> None:
    assert typing.get_fully_qualified_name(input_) == expected_output


def test_get_type_by_fully_qualified_name() -> None:
    assert typing.get_type_by_fully_qualified_name('collections::deque') is deque


# Function local types not supported!
# def test_get_function_local_type_by_fully_qualified_named() -> None:
#     class Local:
#         pass

#     name = typing.get_fully_qualified_name(Local)
#     assert typing.get_type_by_fully_qualified_name(name) is Local
