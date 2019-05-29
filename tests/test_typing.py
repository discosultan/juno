from juno import typing


def test_get_input_type_hints():
    assert typing.get_input_type_hints(foo) == {'a': int}


def test_filter_member_args():
    assert typing.filter_member_args(foo, {'a': 1, 'b': 2}) == {'a': 1}


def foo(a: int) -> int:
    return a
