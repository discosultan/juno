from decimal import Decimal

import pytest

from juno import Fees, Fill, Fills
from juno.agents import Agent
from juno.agents.summary import Position, TradingSummary
from juno.filters import Filters
from juno.plugins import discord
from juno.time import HOUR_MS

from .utils import full_path, new_candle


def get_dummy_trading_summary():
    return TradingSummary(
        exchange='dummy_exchange',
        symbol='eth-btc',
        interval=HOUR_MS,
        start=0,
        quote=Decimal(1),
        fees=Fees.none(),
        filters=Filters.none())


class Dummy(Agent):
    pass


@pytest.fixture
async def agent(config):
    async with Dummy(components={}, agent_config=config) as client:
        yield client


@pytest.mark.manual
@pytest.mark.plugin
async def test_discord(loop, request, config, agent: Agent):
    skip_non_configured(request, config)

    ee = agent.ee
    agent.result = get_dummy_trading_summary()
    async with discord.activate(agent, config['discord']):
        candle = new_candle(time=0, close=Decimal(1), volume=Decimal(10))
        pos = Position(
            time=candle.time,
            fills=Fills([
                Fill(price=Decimal(1), size=Decimal(1), fee=Decimal(0), fee_asset='btc')
            ]))
        await ee.emit('position_opened', pos)
        candle = new_candle(time=HOUR_MS, close=Decimal(2), volume=Decimal(10))
        pos.close(
            time=candle.time,
            fills=Fills([
                Fill(price=Decimal(2), size=Decimal(1), fee=Decimal(0), fee_asset='eth')
            ]))
        await ee.emit('position_closed', pos)
        await ee.emit('finished')
        await ee.emit('img_saved', full_path('/data/dummy_img.png'))


def skip_non_configured(request, config):
    markers = ['manual', 'plugin']
    if request.config.option.markexpr not in markers:
        pytest.skip(f"Specify {' or '.join(markers)} marker to run!")
    discord_config = config.get('discord', {})
    if 'token' not in discord_config or 'dummy' not in discord_config.get('channel_id', {}):
        pytest.skip("Discord params not configured")
