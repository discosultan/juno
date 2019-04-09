# import asyncio
# import env
# from juno.agents import TradingSummary
# from juno.models import *
# import juno.plugins.discord as discord
# from juno.utils import *
# import os
# from pathlib import Path
# import unittest


# def get_dummy_trading_summary(ee):
#     ap_info = AssetPairInfo(0, 'eth-btc', 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
#     acc_info = AccountInfo(0, 0.0, 1.0, Fees(0.0, 0.0))
#     return TradingSummary(ee, 'dummy_exchange', 'dummy_strategy', MS_IN_HOUR, ap_info, acc_info)


# @pytest.mark.manual
# @unittest.skipIf(
#     os.environ.get('JUNO_DISCORD_CHANNEL_TEST') is None or
#     os.environ.get('JUNO_DISCORD_TOKEN') is None,
#     'setup Discord env vars')
# async def test_discord():
#     ee = EventEmitter()
#     async with discord.start(os.environ['JUNO_DISCORD_CHANNEL_TEST'],
#                              os.environ['JUNO_DISCORD_TOKEN'], ee):
#         summary = get_dummy_trading_summary(ee)
#         candle = Candle(0, 0.0, 0.0, 0.0, 0.1, 10.0)
#         await ee.emit('candle', candle, True)
#         pos = Position(candle.time, 10.0, -1.0)
#         await ee.emit('pos_opened', pos)
#         candle = Candle(MS_IN_HOUR, 0.0, 0.0, 0.0, 0.2, 10.0)
#         await ee.emit('candle', candle, True)
#         pos.close(candle.time, 10.0, -1.0)
#         await ee.emit('pos_closed', pos)
#         await ee.emit('summary', summary)
#         await ee.emit('img_saved', str(Path(__file__).parent.joinpath('dummy_img.png')))
