from juno import AccountInfo, Candle, Fees, SymbolInfo
from juno.agents import Agent
from juno.agents.summary import Position, TradingSummary
from juno.plugins import discord
from juno.time import HOUR_MS

import pytest


def get_dummy_trading_summary(ee):
    ap_info = SymbolInfo(0, 'eth-btc', 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    acc_info = AccountInfo(0, 0.0, 1.0, Fees(0.0, 0.0))
    return TradingSummary(ee, 'dummy_exchange', 'dummy_strategy', HOUR_MS, ap_info, acc_info)


class Test(Agent):
    pass


@pytest.fixture
async def agent():
    async with Test as client:
        yield client


@pytest.mark.manual
async def test_discord(loop, request, config, agent):
    skip_non_configured(request, config)

    ee = agent.ee
    async with discord.activate(agent, config):
        summary = get_dummy_trading_summary(ee)
        candle = Candle(0, 0.0, 0.0, 0.0, 0.1, 10.0)
        await ee.emit('candle', candle, True)
        pos = Position(candle.time, 10.0, -1.0)
        await ee.emit('pos_opened', pos)
        candle = Candle(HOUR_MS, 0.0, 0.0, 0.0, 0.2, 10.0)
        await ee.emit('candle', candle, True)
        pos.close(candle.time, 10.0, -1.0)
        await ee.emit('pos_closed', pos)
        await ee.emit('summary', summary)
        # await ee.emit('img_saved', str(Path(__file__).parent.joinpath('dummy_img.png')))


def skip_non_configured(request, config):
    if request.config.option.markexpr != 'manual':
        pytest.skip("Specify 'manual' marker to run! These are run manually as they integrate "
                    "with external services")
    if 'JUNO__DISCORD__TOKEN' not in config or 'JUNO__DISCORD__CHANNEL_ID__TEST' not in config:
        pytest.skip("Discord params not configured")
