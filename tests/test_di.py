import itertools
from typing import Callable, Optional

import pytest

from juno import di

counter = itertools.count(start=1)


@pytest.fixture
def container():
    return di.Container()


def test_resolve_no_deps(container):
    assert container.resolve(Foo)


def test_resolve_implicit_dep(container):
    # Foo is resolved automatically as singleton.
    assert container.resolve(Bar)


def test_resolve_added_instance_dep(container):
    foo = Foo()
    container.add_singleton_instance(Foo, lambda: foo)
    bar = container.resolve(Bar)
    assert bar.foo == foo


def test_resolve_added_type_dep(container):
    container.add_singleton_type(Foo, lambda: Foo)
    bar = container.resolve(Bar)
    assert isinstance(bar.foo, Foo)


async def test_aenter(container):
    baz = container.resolve(Baz)
    async with container:
        assert baz.bar.foo.count == 1
        assert baz.bar.count == 2


def test_map_dependencies():
    foo = Foo()
    bar = Bar(foo)
    baz = Baz(bar)
    assert di.map_dependencies({
        Foo: foo,
        Bar: bar,
        Baz: baz,
    }) == {
        baz: [bar],
        bar: [foo],
        foo: [],
    }


def test_list_dependencies_in_init_order():
    foo = Foo()
    bar = Bar(foo)
    baz = Baz(bar)
    dep_map = {
        baz: [bar],
        bar: [foo],
        foo: [],
    }
    assert di.list_dependencies_in_init_order(dep_map) == [
        [foo],
        [bar],
        [baz],
    ]


def test_no_duplicates_when_same_abstract_and_concrete(container):
    container.add_singleton_type(Foo, lambda: Foo2)
    result1 = container.resolve(Foo)
    result2 = container.resolve(Foo2)
    assert isinstance(result1, Foo2)
    assert result1 == result2


def test_dependency_with_default_values(container):
    result = container.resolve(Qux)
    assert isinstance(result, Qux)
    assert result.factory() == 1
    assert result.number == 1
    assert result.missing is None


def test_type_error_on_missing_dep(container):
    with pytest.raises(TypeError):
        container.resolve(Quux)


def test_optional_dependency_added(container):
    corge = container.resolve(Corge)
    assert corge.foo


class Foo:
    count = 0

    async def __aenter__(self):
        self.count = next(counter)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


class Foo2(Foo):
    pass


class Bar:
    count = 0

    def __init__(self, foo: Foo) -> None:
        self.foo = foo
        self.counter = counter

    async def __aenter__(self):
        self.count = next(counter)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


class Baz:
    def __init__(self, bar: Bar) -> None:
        self.bar = bar


class Qux:
    def __init__(
        self,
        factory: Callable[[], int] = lambda: 1,
        number: int = 1,
        missing: Optional[int] = None,
    ) -> None:
        self.factory = factory
        self.number = number
        self.missing = missing


class Quux:
    def __init__(self, factory: Callable[[], int]) -> None:
        self.factory = factory


class Corge:
    def __init__(self, foo: Optional[Foo] = None):
        self.foo = foo
