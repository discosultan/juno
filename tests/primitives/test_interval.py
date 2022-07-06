import pytest

from juno.primitives.interval import Interval_


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        [Interval_.DAY * 2, "2d"],
        [123, "123ms"],
        [1234, "1s234ms"],
        [0, "0ms"],
    ],
)
def test_format(input_, expected_output) -> None:
    assert Interval_.format(input_) == expected_output


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        ["1d", Interval_.DAY],
        ["2d", Interval_.DAY * 2],
        ["1s1ms", Interval_.SEC + 1],
        ["1m1s", Interval_.MIN + Interval_.SEC],
    ],
)
def test_parse(input_, expected_output) -> None:
    output = Interval_.parse(input_)
    assert output == expected_output
