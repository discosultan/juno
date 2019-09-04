from statistics import mean

import pytest

from juno import Trend, utils


@pytest.mark.parametrize(
    'input,expected_output', [([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])]
)
def test_merge_adjacent_spans(input, expected_output):
    output = list(utils.merge_adjacent_spans(input))
    assert output == expected_output


@pytest.mark.parametrize(
    'start,end,spans,expected_output', [(0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]),
                                        (2, 5, [(1, 3), (4, 6)], [(3, 4)])]
)
def test_generate_missing_spans(start, end, spans, expected_output):
    output = list(utils.generate_missing_spans(start, end, spans))
    assert output == expected_output


def test_page():
    pages = list(utils.page(start=0, end=5, interval=1, limit=2))
    assert len(pages) == 3
    assert pages[0][0] == 0
    assert pages[0][1] == 2
    assert pages[1][0] == 2
    assert pages[1][1] == 4
    assert pages[2][0] == 4
    assert pages[2][1] == 5


def test_recursive_iter():
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


def test_unpack_symbol():
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_flatten():
    expected_output = [35, 53, 525, 6743, 64, 63, 743, 754, 757]
    output = list(utils.flatten([35, 53, [525, 6743], 64, 63, [743, 754, 757]]))
    assert output == expected_output


def test_persistence_level_0_allow_initial_trend():
    persistence = utils.Persistence(level=0, allow_initial_trend=True)
    assert persistence.update(Trend.UP) == (Trend.UP, True)
    assert persistence.update(Trend.UP) == (Trend.UP, False)
    assert persistence.update(Trend.DOWN) == (Trend.DOWN, True)
    assert persistence.update(Trend.UNKNOWN) == (Trend.UNKNOWN, True)
    assert persistence.update(Trend.UP) == (Trend.UP, True)


def test_persistence_level_0_disallow_initial_trend():
    persistence = utils.Persistence(level=0, allow_initial_trend=False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)


def test_persistence_level_0_disallow_initial_trend_starting_with_unknown_does_not_skip_initial():
    persistence = utils.Persistence(level=0, allow_initial_trend=False)
    assert persistence.update(Trend.UNKNOWN) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UP, True)


def test_persistence_level_1_allow_initial_trend():
    persistence = utils.Persistence(level=1, allow_initial_trend=True)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UP, True)
    assert persistence.update(Trend.UP) == (Trend.UP, False)
    assert persistence.update(Trend.DOWN) == (Trend.UP, False)
    assert persistence.update(Trend.DOWN) == (Trend.DOWN, True)
    assert persistence.update(Trend.UNKNOWN) == (Trend.DOWN, False)
    assert persistence.update(Trend.UNKNOWN) == (Trend.UNKNOWN, True)


def test_persistence_level_1_disallow_initial_trend():
    persistence = utils.Persistence(level=1, allow_initial_trend=False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)


def test_persistence_level_1_disallow_initial_trend_starting_with_unknown_does_not_skip_initial():
    persistence = utils.Persistence(level=1, allow_initial_trend=False)
    assert persistence.update(Trend.UNKNOWN) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UP, True)


def test_persistence_level_1_disallow_initial_trend_starting_with_up_does_not_skip_initial():
    persistence = utils.Persistence(level=1, allow_initial_trend=False)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.DOWN) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.DOWN) == (Trend.DOWN, True)


def test_persistence_level_1_allow_initial_trend_change_resets_age():
    persistence = utils.Persistence(level=1, allow_initial_trend=True)
    assert persistence.update(Trend.UP) == (Trend.UNKNOWN, False)
    assert persistence.update(Trend.UP) == (Trend.UP, True)
    assert persistence.update(Trend.DOWN) == (Trend.UP, False)
    assert persistence.update(Trend.UP) == (Trend.UP, False)
    assert persistence.update(Trend.DOWN) == (Trend.UP, False)
    assert persistence.update(Trend.DOWN) == (Trend.DOWN, True)


def test_circular_buffer():
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


async def test_event_emitter():
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
def test_chunks(input, count, expected_output):
    output = list(utils.chunks(input, count))
    assert output == expected_output


def test_get_args_by_param_names():
    params = ['foo', 'bar', 'baz']
    args = [1, 2, 3]
    output = list(utils.get_args_by_params(params, args, ['foo', 'baz']))
    assert output == [1, 3]
