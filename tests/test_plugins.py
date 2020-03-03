from decimal import Decimal

import pytest

from juno import Candle, Fill
from juno.agents import Agent
from juno.time import DAY_MS
from juno.trading import Position, TradingSummary
from juno.utils import full_path


@pytest.mark.manual
@pytest.mark.plugin
async def test_discord(request, config) -> None:
    skip_non_configured(request, config)

    from juno.plugins import discord

    agent = Dummy()
    agent.result = TradingSummary(start=0, quote=Decimal('1.0'))
    async with discord.activate(agent, config['discord']):
        candle = Candle(time=0, close=Decimal('1.0'), volume=Decimal('10.0'))
        pos = Position(
            symbol='eth-btc',
            time=candle.time,
            fills=[
                Fill(price=Decimal('1.0'), size=Decimal('1.0'), fee=Decimal('0.0'),
                     fee_asset='btc')
            ]
        )
        await agent.emit('position_opened', pos)
        candle = Candle(time=DAY_MS, close=Decimal('2.0'), volume=Decimal('10.0'))
        pos.close(
            time=candle.time,
            fills=[
                Fill(price=Decimal('2.0'), size=Decimal('1.0'), fee=Decimal('0.0'),
                     fee_asset='eth')
            ]
        )
        agent.result.append_position(pos)
        assert pos.closing_time
        agent.result.finish(pos.closing_time + DAY_MS)
        await agent.emit('position_closed', pos)
        await agent.emit('finished')
        await agent.emit('image', full_path(__file__, '/data/dummy_img.png'))
        try:
            raise Exception('Expected error.')
        except Exception as exc:
            await agent.emit('errored', exc)


def skip_non_configured(request, config):
    markers = ['manual', 'plugin']
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    discord_config = config.get('discord', {})
    if 'token' not in discord_config or 'dummy' not in discord_config.get('channel_id', {}):
        pytest.skip("Discord params not configured")


class Dummy(Agent):
    pass
