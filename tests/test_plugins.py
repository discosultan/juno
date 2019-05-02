from decimal import Decimal

import pytest

from juno import Candle, Fees, Fill, Fills, SymbolInfo
from juno.agents import Agent
from juno.agents.summary import Position, TradingSummary
from juno.plugins import discord
from juno.time import HOUR_MS

from .utils import full_path


def get_dummy_trading_summary():
    ap_info = SymbolInfo(Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0))
    fees = Fees(Decimal(0), Decimal(0))
    return TradingSummary('dummy_exchange', 'eth-btc', HOUR_MS, 0, 1, Decimal(1), fees, ap_info)


class Dummy(Agent):
    pass


@pytest.fixture
async def agent(config):
    async with Dummy(components={}, agent_config=config) as client:
        yield client


@pytest.mark.manual
async def test_discord(loop, request, config, agent: Agent):
    skip_non_configured(request, config)

    ee = agent.ee
    agent.result = get_dummy_trading_summary()
    async with discord.activate(agent, config['discord']):
        candle = Candle(0, Decimal(0), Decimal(0), Decimal(0), Decimal(1), Decimal(10))
        pos = Position(
            time=candle.time,
            fills=Fills([
                Fill(price=Decimal(1), size=Decimal(1), fee=Decimal(0), fee_asset='btc')
            ]))
        await ee.emit('position_opened', agent, pos)
        candle = Candle(HOUR_MS, Decimal(0), Decimal(0), Decimal(0), Decimal(2), Decimal(10))
        pos.close(
            time=candle.time,
            fills=Fills([
                Fill(price=Decimal(2), size=Decimal(1), fee=Decimal(0), fee_asset='eth')
            ]))
        await ee.emit('position_closed', agent, pos)
        await ee.emit('finished', agent)
        await ee.emit('img_saved', full_path('/data/dummy_img.png'))


def skip_non_configured(request, config):
    if request.config.option.markexpr != 'manual':
        pytest.skip("Specify 'manual' marker to run! These are run manually as they integrate "
                    "with external services")
    discord_config = config.get('discord', {})
    if 'token' not in discord_config or 'dummy' not in discord_config.get('channel_id', {}):
        pytest.skip("Discord params not configured")
