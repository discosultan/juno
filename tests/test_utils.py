from statistics import mean

from juno import utils


def test_replace_secrets() -> None:
    input = {'foo': 'hello', 'secret_bar': 'world'}
    output = utils.replace_secrets(input)

    assert all(k in output for k in input.keys())
    assert output['foo'] == 'hello'
    assert output['secret_bar'] != input['secret_bar']


def test_unpack_symbol() -> None:
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_circular_buffer() -> None:
    buffer = utils.CircularBuffer(size=2, default=0)

    buffer.push(2)
    buffer.push(4)

    assert len(buffer) == 2
    assert sum(buffer) == 6
    assert mean(buffer) == 3
    assert min(buffer) == 2
    assert max(buffer) == 4

    buffer.push(6)

    assert len(buffer) == 2
    assert sum(buffer) == 10
    assert mean(buffer) == 5
    assert min(buffer) == 4
    assert max(buffer) == 6


async def test_event_emitter() -> None:
    ee = utils.EventEmitter()
    exc = Exception('Expected error.')

    @ee.on('foo')
    async def succeed():
        return 1

    @ee.on('foo')
    async def error():
        raise exc

    assert await ee.emit('foo') == [1, exc]


def test_tonamedtuple() -> None:
    class Foo:
        a: int = 1
        _b: int = 2

        @property
        def c(self) -> int:
            return 3

    foo = Foo()
    x = utils.tonamedtuple(foo)

    assert x.a == 1
    assert not getattr(x, 'b', None)
    assert x.c == 3
    utils.tonamedtuple(foo)  # Ensure can be called twice.
