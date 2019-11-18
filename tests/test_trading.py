from decimal import Decimal

import pytest

from juno import Fees, Fill, Fills, Filters, Position, TradingSummary
from juno.time import HOUR_MS

from .utils import new_candle, new_closed_position


def test_position():
    pos = Position(
        time=0,
        fills=Fills([
            Fill(price=Decimal('2.0'), size=Decimal('6.0'), fee=Decimal('2.0'), fee_asset='btc')
        ])
    )
    pos.close(
        time=1,
        fills=Fills([
            Fill(price=Decimal('2.0'), size=Decimal('2.0'), fee=Decimal('1.0'), fee_asset='eth')
        ])
    )

    assert pos.cost == 12  # 6 * 2
    assert pos.gain == 3  # 2 * 2 - 1
    assert pos.dust == 2  # 6 - 2 - 2
    assert pos.profit == -9
    assert pos.duration == 1
    assert pos.start == 0
    assert pos.end == 1
    assert pos.roi == Decimal('-0.75')
    assert pos.annualized_roi == -1


def test_position_annualized_roi_overflow():
    pos = Position(
        time=0,
        fills=Fills([
            Fill(price=Decimal('1.0'), size=Decimal('1.0'), fee=Decimal('0.0'), fee_asset='eth')
        ]))
    pos.close(
        time=2,
        fills=Fills([
            Fill(price=Decimal('2.0'), size=Decimal('1.0'), fee=Decimal('0.0'), fee_asset='btc')
        ])
    )

    assert pos.annualized_roi == Decimal('Inf')


def test_summary():
    summary = TradingSummary(
        interval=HOUR_MS, start=0, quote=Decimal('100.0'), fees=Fees.none(), filters=Filters.none()
    )
    summary.append_candle(new_candle())
    # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
    # Series: 100, 110, 99, 103.95, 93.55, 102.91
    positions = [
        new_closed_position(Decimal('10.0')),
        new_closed_position(Decimal('-11.0')),
        new_closed_position(Decimal('4.95')),
        new_closed_position(Decimal('-10.4')),
        new_closed_position(Decimal('9.36')),
    ]
    for position in positions:
        summary.append_position(position)

    assert summary.cost == Decimal('100.0')
    assert summary.gain == Decimal('102.91')
    assert summary.profit == Decimal('2.91')
    assert summary.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_summary():
    summary = TradingSummary(
        interval=HOUR_MS, start=0, quote=Decimal('100.0'), fees=Fees.none(), filters=Filters.none()
    )
    assert summary.cost == 100
    assert summary.gain == 100
    assert summary.profit == 0
    assert summary.max_drawdown == 0
