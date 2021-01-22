import itertools
from typing import Any, Callable, Optional

import pytest

from juno import di

counter = itertools.count(start=1)


@pytest.fixture
def container():
    return di.Container()


def test_resolve_no_deps(container: di.Container) -> None:
    assert container.resolve(Foo)


def test_not_registered_not_resolved_implicitly(container: di.Container) -> None:
    with pytest.raises(TypeError):
        assert container.resolve(Bar)


def test_resolve_added_instance_dep(container: di.Container) -> None:
    foo = Foo()
    container.add_singleton_instance(Foo, lambda: foo)
    bar = container.resolve(Bar)
    assert bar.foo == foo


def test_resolve_added_type_dep(container: di.Container) -> None:
    container.add_singleton_type(Foo, lambda: Foo)
    bar = container.resolve(Bar)
    assert isinstance(bar.foo, Foo)


async def test_aenter(container: di.Container) -> None:
    container.add_singleton_type(Foo)
    container.add_singleton_type(Bar)
    baz = container.resolve(Baz)
    async with container:
        assert baz.bar.foo.count == 1
        assert baz.bar.count == 2


def test_map_dependencies() -> None:
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


def test_list_dependencies_in_init_order() -> None:
    foo = Foo()
    bar = Bar(foo)
    baz = Baz(bar)
    dep_map: dict[Any, list[Any]] = {
        baz: [bar],
        bar: [foo],
        foo: [],
    }
    assert di.list_dependencies_in_init_order(dep_map) == [
        [foo],
        [bar],
        [baz],
    ]


def test_no_duplicates_when_same_abstract_and_concrete(container: di.Container) -> None:
    class Qux(Foo):
        pass

    container.add_singleton_type(Foo, lambda: Qux)
    result1 = container.resolve(Foo)
    result2 = container.resolve(Qux)
    assert isinstance(result1, Qux)
    assert result1 == result2


def test_dependency_with_default_value(container: di.Container) -> None:
    class Qux:
        def __init__(self, factory: Callable[[], int] = lambda: 1) -> None:
            self.factory = factory

    result = container.resolve(Qux)
    assert isinstance(result, Qux)
    assert result.factory() == 1


def test_type_error_on_missing_dep(container: di.Container) -> None:
    class Qux:
        def __init__(self, factory: Callable[[], int]) -> None:
            self.factory = factory

    with pytest.raises(TypeError):
        container.resolve(Qux)


def test_optional_dependency_added(container: di.Container) -> None:
    class Qux:
        def __init__(self, value: Optional[int] = None) -> None:
            self.value = value

    container.add_singleton_type(int)
    result = container.resolve(Qux)
    assert result.value == 0


def test_falls_back_to_default_if_factories_fail(container: di.Container) -> None:
    class Qux:
        def __init__(self, value: int = 1) -> None:
            self.value = value

    container.add_singleton_instance(int, lambda: raise_type_error())
    container.add_singleton_type(int, lambda: raise_type_error())
    assert container.resolve(Qux).value == 1


class Foo:
    count = 0

    async def __aenter__(self):
        self.count = next(counter)

    async def __aexit__(self, exc_type, exc, tb) -> None:
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


def raise_type_error():
    raise TypeError()
