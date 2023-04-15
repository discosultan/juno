from decimal import Decimal

import pytest

from juno import AssetInfo, Fill
from juno.statistics import CoreStatistics
from juno.trading import CloseReason, Position, TradingSummary


def test_long_position() -> None:
    open_pos = Position.OpenLong.build(
        exchange="exchange",
        symbol="eth-btc",
        time=0,
        fills=[
            Fill(
                price=Decimal("2.0"),
                size=Decimal("6.0"),
                quote=Decimal("12.0"),
                fee=Decimal("2.0"),
                fee_asset="eth",
            )
        ],
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )
    pos = open_pos.close(
        time=1,
        fills=[
            Fill(
                price=Decimal("2.0"),
                size=Decimal("2.0"),
                quote=Decimal("4.0"),
                fee=Decimal("1.0"),
                fee_asset="btc",
            )
        ],
        reason=CloseReason.STRATEGY,
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )

    assert pos.cost == 12  # 6 * 2
    assert pos.gain == 3  # 2 * 2 - 1
    assert pos.dust == 2  # 6 - 2 - 2
    assert pos.profit == -9
    assert pos.duration == 1
    assert pos.open_time == 0
    assert pos.close_time == 1
    assert pos.roi == Decimal("-0.75")
    assert pos.annualized_roi == -1


def test_long_position_annualized_roi_overflow() -> None:
    open_pos = Position.OpenLong.build(
        exchange="exchange",
        symbol="eth-btc",
        time=0,
        fills=[
            Fill(
                price=Decimal("1.0"),
                size=Decimal("1.0"),
                quote=Decimal("1.0"),
                fee=Decimal("0.0"),
                fee_asset="eth",
            )
        ],
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )
    pos = open_pos.close(
        time=2,
        fills=[
            Fill(
                price=Decimal("2.0"),
                size=Decimal("1.0"),
                quote=Decimal("2.0"),
                fee=Decimal("0.0"),
                fee_asset="btc",
            )
        ],
        reason=CloseReason.STRATEGY,
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )

    assert pos.annualized_roi == Decimal("Inf")


def test_trading_summary() -> None:
    summary = TradingSummary(
        start=0,
        end=1,
        starting_assets={
            "btc": Decimal("100.0"),
        },
        # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
        # Series: 100, 110, 99, 103.95, 93.55, 102.91
        positions=[
            new_closed_long_position(Decimal("10.0")),
            new_closed_long_position(Decimal("-11.0")),
            new_closed_long_position(Decimal("4.95")),
            new_closed_long_position(Decimal("-10.4")),
            new_closed_long_position(Decimal("9.36")),
        ],
    )

    stats = CoreStatistics.compose(summary)
    assert stats.cost == Decimal("100.0")
    assert stats.gain == Decimal("102.91")
    assert stats.profit == Decimal("2.91")
    assert stats.max_drawdown == pytest.approx(Decimal("0.1495"), Decimal("0.001"))


def test_empty_trading_summary() -> None:
    summary = TradingSummary(
        start=0,
        end=1,
        starting_assets={
            "btc": Decimal("100.0"),
        },
        positions=[],
    )
    stats = CoreStatistics.compose(summary)
    assert stats.cost == 100
    assert stats.gain == 100
    assert stats.profit == 0
    assert stats.max_drawdown == 0


def new_closed_long_position(profit: Decimal) -> Position.Long:
    size = abs(profit)
    open_price = Decimal("2.0")
    close_price = Decimal("3.0") if profit >= 0 else Decimal("1.0")
    open_pos = Position.OpenLong.build(
        exchange="exchange",
        symbol="eth-btc",
        time=0,
        fills=[
            Fill.with_computed_quote(price=open_price, size=size, fee_asset="eth"),
        ],
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )
    return open_pos.close(
        time=1,
        fills=[
            Fill.with_computed_quote(price=close_price, size=size, fee_asset="btc"),
        ],
        reason=CloseReason.STRATEGY,
        base_asset_info=AssetInfo(),
        quote_asset_info=AssetInfo(),
    )
