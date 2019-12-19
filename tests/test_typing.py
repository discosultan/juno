from typing import List, NamedTuple

import pytest

from juno import typing


def foo(a: int) -> int:
    return a


class Bar(NamedTuple):
    value: int


def test_get_input_type_hints():
    assert typing.get_input_type_hints(foo) == {'a': int}


def test_filter_member_args():
    assert typing.filter_member_args(foo, {'a': 1, 'b': 2}) == {'a': 1}


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
