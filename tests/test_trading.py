from decimal import Decimal

import pytest

from juno import Fill
from juno.trading import CloseReason, Position, TradingSummary


def test_long_position() -> None:
    open_pos = Position.OpenLong(
        exchange='exchange',
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('6.0'), quote=Decimal('12.0'),
                fee=Decimal('2.0'), fee_asset='eth'
            )
        ],
    )
    pos = open_pos.close(
        time=1,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('2.0'), quote=Decimal('4.0'),
                fee=Decimal('1.0'), fee_asset='btc'
            )
        ],
        reason=CloseReason.STRATEGY,
    )

    assert pos.cost == 12  # 6 * 2
    assert pos.gain == 3  # 2 * 2 - 1
    assert pos.dust == 2  # 6 - 2 - 2
    assert pos.profit == -9
    assert pos.duration == 1
    assert pos.open_time == 0
    assert pos.close_time == 1
    assert pos.roi == Decimal('-0.75')
    assert pos.annualized_roi == -1


def test_long_position_annualized_roi_overflow() -> None:
    open_pos = Position.OpenLong(
        exchange='exchange',
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(
                price=Decimal('1.0'), size=Decimal('1.0'), quote=Decimal('1.0'),
                fee=Decimal('0.0'), fee_asset='eth'
            )
        ],
    )
    pos = open_pos.close(
        time=2,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('1.0'), quote=Decimal('2.0'),
                fee=Decimal('0.0'), fee_asset='btc'
            )
        ],
        reason=CloseReason.STRATEGY,
    )

    assert pos.annualized_roi == Decimal('Inf')


def test_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'), quote_asset='btc')
    # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
    # Series: 100, 110, 99, 103.95, 93.55, 102.91
    positions = [
        new_closed_long_position(Decimal('10.0')),
        new_closed_long_position(Decimal('-11.0')),
        new_closed_long_position(Decimal('4.95')),
        new_closed_long_position(Decimal('-10.4')),
        new_closed_long_position(Decimal('9.36')),
    ]
    for position in positions:
        summary.append_position(position)

    assert summary.cost == Decimal('100.0')
    assert summary.gain == Decimal('102.91')
    assert summary.profit == Decimal('2.91')
    assert summary.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'), quote_asset='btc')
    assert summary.cost == 100
    assert summary.gain == 100
    assert summary.profit == 0
    assert summary.max_drawdown == 0


def test_trading_summary_end() -> None:
    summary = TradingSummary(start=0, quote=Decimal('1.0'), quote_asset='btc')

    summary.append_position(Position.Long(
        exchange='exchange',
        symbol='eth-btc',
        open_time=0,
        open_fills=[],
        close_time=1,
        close_fills=[],
        close_reason=CloseReason.STRATEGY,
    ))
    assert summary.end == 1

    summary.finish(2)
    assert summary.end == 2


def new_closed_long_position(profit: Decimal) -> Position.Long:
    size = abs(profit)
    price = Decimal('1.0') if profit >= 0 else Decimal('-1.0')
    open_pos = Position.OpenLong(
        exchange='exchange',
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(price=Decimal('0.0'), size=size, quote=Decimal('0.0'), fee_asset='eth'),
        ],
    )
    return open_pos.close(
        time=1,
        fills=[
            Fill(price=price, size=size, quote=Decimal(price * size), fee_asset='btc'),
        ],
        reason=CloseReason.STRATEGY,
    )
