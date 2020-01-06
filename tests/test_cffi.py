from decimal import Decimal
from typing import List, NamedTuple, _GenericAlias  # type: ignore

import pytest

from juno import cffi


@pytest.fixture
def cdef_builder():
    return cffi.CDefBuilder()


def test_cdef_builder_function(cdef_builder):
    output = cdef_builder.function(bar)
    assert output == '''uint32_t bar(
    uint32_t x,
    double y);
'''


def test_cdef_builder_function_from_params(cdef_builder):
    output = cdef_builder.function_from_params('bar', int, ('x', int), ('y', Decimal))
    assert output == '''uint32_t bar(
    uint32_t x,
    double y);
'''


def test_cdef_builder_function_from_params_custom_mapping():
    cdef_builder = cffi.CDefBuilder({Baz: 'uint64_t'})
    output = cdef_builder.function_from_params('baz', Baz, ('x', int), ('y', Baz))
    assert output == '''uint64_t baz(
    uint32_t x,
    uint64_t y);
'''


def test_cdef_builder_function_from_params_missing_mapping(cdef_builder):
    output = cdef_builder.function_from_params('temp', Foo)
    assert output == '''Foo temp();
'''


def test_build_function_from_params_void_return(cdef_builder):
    output = cdef_builder.function_from_params('temp', None)
    assert output == '''void temp();
'''


def test_cdef_builder_function_from_params_list(cdef_builder):
    output = cdef_builder.function_from_params('temp', int, ('values', List[int]))
    assert output == '''uint32_t temp(
    const uint32_t* values,
    uint32_t values_length);
'''


def test_cdef_builder_struct(cdef_builder):
    output = cdef_builder.struct(Foo)
    assert output == '''typedef struct {
    uint32_t x;
    double y;
} Foo;
'''


def test_cdef_builder_struct_exclude_field(cdef_builder):
    output = cdef_builder.struct(Foo, exclude=['x'])
    assert output == '''typedef struct {
    double y;
} Foo;
'''


def test_cdef_builder_struct_from_fields(cdef_builder):
    output = cdef_builder.struct_from_fields('Foo', ('x', int), ('y', Decimal))
    assert output == '''typedef struct {
    uint32_t x;
    double y;
} Foo;
'''


class Foo(NamedTuple):
    x: int
    y: Decimal


def bar(x: int, y: Decimal) -> int:
    pass


Baz = _GenericAlias(int, (), inst=False, name='Baz')
