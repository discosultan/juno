from decimal import Decimal

import pytest

from juno import filters


@pytest.mark.parametrize(
    'price,min_,max_,step,expected_output', [
        (
            Decimal('0.000005540'),
            Decimal('1E-8'),
            Decimal('100000.00000000'),
            Decimal('1E-8'),
            Decimal('0.00000554')
        ),
        (
            Decimal('1.0'),
            Decimal('0.0'),
            Decimal('0.0'),
            Decimal('0.0'),
            Decimal('1.0')
        ),
        # step is 0
        (
            Decimal('2.0'),
            Decimal('1.0'),
            Decimal('3.0'),
            Decimal('0.0'),
            Decimal('2.0')
        ),
    ]
)
def test_price_round_down(price, min_, max_, step, expected_output) -> None:
    filter_ = filters.Price(min=min_, max=max_, step=step)
    output = filter_.round_down(price)
    assert output == expected_output


@pytest.mark.parametrize(
    'size,min_,max_,step,expected_output',
    [
        # min
        (
            Decimal('0.1'),
            Decimal('0.2'),
            Decimal('0.3'),
            Decimal('0.1'),
            Decimal('0.0')
        ),
        # max
        (
            Decimal('0.4'),
            Decimal('0.2'),
            Decimal('0.3'),
            Decimal('0.1'),
            Decimal('0.3')
        ),
        # step
        (
            Decimal('0.25'),
            Decimal('0.2'),
            Decimal('0.3'),
            Decimal('0.1'),
            Decimal('0.2')
        ),
        # rounding down to step
        (
            Decimal('1412.10939049659'),
            Decimal('0.00100000'),
            Decimal('100000.00000000'),
            Decimal('0.00100000'),
            Decimal('1412.109')
        ),
        # step is 0
        (
            Decimal('2.0'),
            Decimal('1.0'),
            Decimal('3.0'),
            Decimal('0.0'),
            Decimal('2.0')
        ),
    ]
)
def test_size_round_down(size, min_, max_, step, expected_output) -> None:
    filter_ = filters.Size(min=min_, max=max_, step=step)
    output = filter_.round_down(size)
    assert output == expected_output


def test_size_default_valid() -> None:
    filter_ = filters.Size()
    assert filter_.valid(Decimal('1.0'))
