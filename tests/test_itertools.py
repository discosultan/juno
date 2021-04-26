import pytest

from juno import itertools


@pytest.mark.parametrize(
    'input_,expected_output', [([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])]
)
def test_merge_adjacent_spans(input_, expected_output) -> None:
    output = list(itertools.merge_adjacent_spans(input_))
    assert output == expected_output


@pytest.mark.parametrize(
    'start,end,spans,expected_output',
    [(0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]), (2, 5, [(1, 3), (4, 6)], [(3, 4)])],
)
def test_generate_missing_spans(start, end, spans, expected_output) -> None:
    output = list(itertools.generate_missing_spans(start, end, spans))
    assert output == expected_output


def test_page() -> None:
    pages = list(itertools.page(start=0, end=5, interval=1, limit=2))
    assert len(pages) == 3
    assert pages[0][0] == 0
    assert pages[0][1] == 2
    assert pages[1][0] == 2
    assert pages[1][1] == 4
    assert pages[2][0] == 4
    assert pages[2][1] == 5


def test_recursive_iter() -> None:
    input_ = {
        'aa': 'ab',
        'ba': {'ca': 'cb'},
        'da': [{'ea': 'eb'}],
    }
    expected_output = [
        (('aa',), 'ab'),
        (('ba', 'ca'), 'cb'),
        (('da', 0, 'ea'), 'eb'),
    ]
    output = list(itertools.recursive_iter(input_))
    assert output == expected_output
