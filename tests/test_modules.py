from collections import deque
from typing import Any

import pytest

from juno import modules


@pytest.mark.parametrize('input_,expected_output', [
    (deque((1, 2, 3)), 'collections::deque'),
    (deque, 'collections::deque'),
])
def test_get_fully_qualified_name(input_: Any, expected_output: str) -> None:
    assert modules.get_fully_qualified_name(input_) == expected_output


def test_get_type_by_fully_qualified_name() -> None:
    assert modules.get_type_by_fully_qualified_name('collections::deque') is deque
