from decimal import Decimal
from typing import Any

import pytest
from pytest_mock import MockerFixture

from juno import Candle, Fill, Interval_
from juno.components import Chandler, Events, Informant
from juno.path import full_path
from juno.trading import CloseReason, Position, TradingSummary


@pytest.mark.manual
@pytest.mark.plugin
async def test_discord(request, config: dict[str, Any], mocker: MockerFixture) -> None:
    skip_non_configured(request, config)

    from juno.plugins.discord import Discord

    events = Events()
    async with Discord(
        chandler=mocker.MagicMock(Chandler),
        informant=mocker.MagicMock(Informant),
        events=events,
        config=config,
    ) as discord:
        await discord.activate("agent", "test")

        await send_test_events(events)


@pytest.mark.manual
@pytest.mark.plugin
async def test_slack(request, config: dict[str, Any]) -> None:
    skip_non_configured(request, config)

    from juno.plugins.slack import Slack

    events = Events()
    slack = Slack(events=events, config=config)
    await slack.activate("agent", "test")

    await send_test_events(events)


async def send_test_events(events: Events):
    trading_summary = TradingSummary(
        start=0,
        end=1,
        starting_assets={
            "btc": Decimal("1.0"),
        },
        positions=[],
    )

    candle = Candle(time=0, close=Decimal("1.0"), volume=Decimal("10.0"))
    open_pos = Position.OpenLong(
        exchange="exchange",
        symbol="eth-btc",
        time=candle.time,
        fills=[
            Fill(
                price=Decimal("1.0"),
                size=Decimal("1.0"),
                quote=Decimal("1.0"),
                fee=Decimal("0.0"),
                fee_asset="btc",
            )
        ],
    )
    await events.emit("agent", "positions_opened", [open_pos], trading_summary)
    candle = Candle(time=Interval_.DAY, close=Decimal("2.0"), volume=Decimal("10.0"))
    pos = open_pos.close(
        time=candle.time,
        fills=[
            Fill(
                price=Decimal("2.0"),
                size=Decimal("1.0"),
                quote=Decimal("2.0"),
                fee=Decimal("0.0"),
                fee_asset="eth",
            )
        ],
        reason=CloseReason.STRATEGY,
    )
    trading_summary = TradingSummary(
        start=0,
        end=pos.close_time + Interval_.DAY,
        starting_assets={
            "btc": Decimal("1.0"),
        },
        positions=[pos],
    )
    await events.emit("agent", "positions_closed", [pos], trading_summary)
    await events.emit("agent", "finished", trading_summary)
    await events.emit("agent", "image", full_path(__file__, "/data/dummy_img.png"))
    await events.emit("agent", "message", "hello")
    try:
        raise Exception("Expected error.")
    except Exception as exc:
        await events.emit("agent", "errored", exc)


def skip_non_configured(request, config):
    markers = ["manual", "plugin"]
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    discord_config = config.get("discord", {})
    if "token" not in discord_config or "dummy" not in discord_config.get("channel_id", {}):
        pytest.skip("Discord params not configured")
