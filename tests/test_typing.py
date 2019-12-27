from typing import Dict, List, NamedTuple, Tuple

import pytest

from juno import typing


def foo(a: int) -> int:
    return a


class Bar(NamedTuple):
    value: int


def test_get_input_type_hints():
    assert typing.get_input_type_hints(foo) == {'a': int}


@pytest.mark.parametrize('input,expected_output', [
    (list, 'list'),
    (List[int], 'typing.List[int]'),
    (Bar, 'Bar'),
])
def test_get_name(input, expected_output):
    assert typing.get_name(input) == expected_output


@pytest.mark.parametrize('input,expected_output', [
    (list, False),
    (List[int], False),
    (Bar, True),
])
def test_isnamedtuple(input, expected_output):
    assert typing.isnamedtuple(input) == expected_output


@pytest.mark.parametrize('input,type_,expected_output', [
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
])
def test_types_match(input, type_, expected_output):
    assert typing.types_match(input, type_) == expected_output
