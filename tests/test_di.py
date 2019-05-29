import itertools

from juno.di import Container

counter = itertools.count(start=1)


def test_resolve_no_deps():
    container = Container()
    assert container.resolve(Foo)


def test_resolve_implicit_dep():
    # Foo is resolved automatically as singleton.
    container = Container()
    assert container.resolve(Bar)


def test_resolve_added_dep():
    container = Container()
    foo = Foo()
    container.add_singleton(Foo, foo)
    bar = container.resolve(Bar)
    assert bar.foo == foo


async def test_aenter():
    container = Container()
    foo = Foo()
    container.add_singleton(Foo, foo)
    bar = Bar(foo)
    container.add_singleton(Bar, bar)
    container.resolve(Baz)
    async with container:
        assert bar.count == 2
        assert foo.count == 1


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
