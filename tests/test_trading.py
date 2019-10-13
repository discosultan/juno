from decimal import Decimal

import pytest

from juno import Fill, Fills, Position, TradingSummary
from juno.time import HOUR_MS

from .utils import new_candle, new_closed_position


def test_position():
    pos = Position(
        time=0,
        fills=Fills([Fill(price=Decimal(2), size=Decimal(6), fee=Decimal(2), fee_asset='btc')])
    )
    pos.close(
        time=1,
        fills=Fills([Fill(price=Decimal(2), size=Decimal(2), fee=Decimal(1), fee_asset='eth')])
    )

    assert pos.cost == Decimal(12)  # 6 * 2
    assert pos.gain == Decimal(3)  # 2 * 2 - 1
    assert pos.dust == Decimal(2)  # 6 - 2 - 2
    assert pos.profit == Decimal(-9)
    assert pos.duration == 1
    assert pos.start == 0
    assert pos.end == 1
    assert pos.roi == Decimal('-0.75')
    assert pos.annualized_roi == Decimal(-1)


def test_summary():
    summary = TradingSummary(interval=HOUR_MS, start=0, quote=Decimal(100))
    summary.append_candle(new_candle())
    # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
    # Series: 100, 110, 99, 103.95, 93.55, 102.91
    positions = [
        new_closed_position(Decimal(10)),
        new_closed_position(Decimal(-11)),
        new_closed_position(Decimal('4.95')),
        new_closed_position(Decimal('-10.4')),
        new_closed_position(Decimal('9.36')),
    ]
    for position in positions:
        summary.append_position(position)

    assert summary.cost == Decimal(100)
    assert summary.gain == Decimal('102.91')
    assert summary.profit == Decimal('2.91')
    assert summary.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_summary():
    summary = TradingSummary(interval=HOUR_MS, start=0, quote=Decimal(100))
    assert summary.cost == Decimal(100)
    assert summary.gain == Decimal(100)
    assert summary.profit == Decimal(0)
    assert summary.max_drawdown == Decimal(0)
