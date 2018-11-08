import pytest

from juno import utils

import env


@pytest.mark.parametrize('input,expected_output', [
    ([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])
])
def test_merge_adjacent_spans(input, expected_output):
    output = list(utils.merge_adjacent_spans(input))
    assert output == expected_output


@pytest.mark.parametrize('start,end,spans,expected_output', [
    (0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]),
    (2, 5, [(1, 3), (4, 6)], [(3, 4)])
])
def test_generate_missing_spans(start, end, spans, expected_output):
    output = list(utils.generate_missing_spans(start, end, spans))
    assert output == expected_output
