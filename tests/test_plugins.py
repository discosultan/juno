from decimal import Decimal
from typing import Any, Dict

import pytest

from juno import Advice, Candle, Fill
from juno.components import Events
from juno.time import DAY_MS
from juno.trading import CloseReason, Position, TradingSummary
from juno.utils import full_path


@pytest.mark.manual
@pytest.mark.plugin
async def test_discord(request, config: Dict[str, Any]) -> None:
    skip_non_configured(request, config)

    from juno.plugins.discord import Discord

    trading_summary = TradingSummary(start=0, quote=Decimal('1.0'), quote_asset='btc')
    events = Events()
    async with Discord(events, config) as discord:
        await discord.activate('agent', 'test')

        candle = Candle(time=0, close=Decimal('1.0'), volume=Decimal('10.0'))
        open_pos = Position.OpenLong(
            exchange='exchange',
            symbol='eth-btc',
            time=candle.time,
            fills=[
                Fill(
                    price=Decimal('1.0'), size=Decimal('1.0'), quote=Decimal('1.0'),
                    fee=Decimal('0.0'), fee_asset='btc'
                )
            ],
        )
        await events.emit('agent', 'position_opened', open_pos, trading_summary)
        candle = Candle(time=DAY_MS, close=Decimal('2.0'), volume=Decimal('10.0'))
        pos = open_pos.close(
            time=candle.time,
            fills=[
                Fill(
                    price=Decimal('2.0'), size=Decimal('1.0'), quote=Decimal('2.0'),
                    fee=Decimal('0.0'), fee_asset='eth'
                )
            ],
            reason=CloseReason.STRATEGY,
        )
        trading_summary.append_position(pos)
        trading_summary.finish(pos.close_time + DAY_MS)
        await events.emit('agent', 'position_closed', pos, trading_summary)
        await events.emit('agent', 'finished', trading_summary)
        await events.emit('agent', 'image', full_path(__file__, '/data/dummy_img.png'))
        await events.emit('agent', 'advice', Advice.LIQUIDATE)
        try:
            raise Exception('Expected error.')
        except Exception as exc:
            await events.emit('agent', 'errored', exc)


def skip_non_configured(request, config):
    markers = ['manual', 'plugin']
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    discord_config = config.get('discord', {})
    if 'token' not in discord_config or 'dummy' not in discord_config.get('channel_id', {}):
        pytest.skip('Discord params not configured')
