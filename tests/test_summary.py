from decimal import Decimal

import simplejson as json

from juno import Fees, Fill, Fills, Filters, Position, TradingSummary
from juno.time import HOUR_MS

from .utils import new_candle


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
    summary = TradingSummary(
        interval=HOUR_MS,
        start=0,
        quote=Decimal(100),
        fees=Fees.none(),
        filters=Filters.none()
    )
    summary.append_candle(new_candle())
    summary.append_position(Position(time=0, fills=Fills([Fill(*([Decimal(1)] * 3), 'eth')])))
    json.dumps(summary, default=lambda o: o.__dict__, use_decimal=True)
