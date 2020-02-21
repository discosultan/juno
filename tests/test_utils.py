from statistics import mean

import pytest

from juno import utils


@pytest.mark.parametrize(
    'input,expected_output', [([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])]
)
def test_merge_adjacent_spans(input, expected_output) -> None:
    output = list(utils.merge_adjacent_spans(input))
    assert output == expected_output


@pytest.mark.parametrize(
    'start,end,spans,expected_output', [(0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]),
                                        (2, 5, [(1, 3), (4, 6)], [(3, 4)])]
)
def test_generate_missing_spans(start, end, spans, expected_output) -> None:
    output = list(utils.generate_missing_spans(start, end, spans))
    assert output == expected_output


def test_page() -> None:
    pages = list(utils.page(start=0, end=5, interval=1, limit=2))
    assert len(pages) == 3
    assert pages[0][0] == 0
    assert pages[0][1] == 2
    assert pages[1][0] == 2
    assert pages[1][1] == 4
    assert pages[2][0] == 4
    assert pages[2][1] == 5


def test_recursive_iter() -> None:
    input = {
        'aa': 'ab',
        'ba': {
            'ca': 'cb'
        },
        'da': [{
            'ea': 'eb'
        }],
    }
    expected_output = [
        (('aa', ), 'ab'),
        (('ba', 'ca'), 'cb'),
        (('da', 0, 'ea'), 'eb'),
    ]
    output = list(utils.recursive_iter(input))
    assert output == expected_output


def test_replace_secrets() -> None:
    input = {'foo': 'hello', 'secret_bar': 'world'}
    output = utils.replace_secrets(input)

    assert all(k in output for k in input.keys())
    assert output['foo'] == 'hello'
    assert output['secret_bar'] != input['secret_bar']


def test_unpack_symbol() -> None:
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_flatten() -> None:
    expected_output = [35, 53, 525, 6743, 64, 63, 743, 754, 757]
    output = list(utils.flatten([35, 53, [525, 6743], 64, 63, [743, 754, 757]]))
    assert output == expected_output


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


@pytest.mark.parametrize(
    'input,count,expected_output', [
        ('ab', 1, ['a', 'b']),
        ('ab', 2, ['ab']),
    ]
)
def test_chunks(input, count, expected_output) -> None:
    output = list(utils.chunks(input, count))
    assert output == expected_output


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
