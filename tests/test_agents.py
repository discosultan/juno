from decimal import Decimal

import pytest

from juno import Balance, Candle, Fees, Side
from juno.agents import Backtest, Live, Paper
from juno.filters import Filters, Price, Size
from juno.time import HOUR_MS
from juno.trading import MissedCandlePolicy
from juno.utils import load_json_file

from . import fakes


async def test_backtest():
    chandler = fakes.Chandler(
        candles=[
            Candle(time=0, close=Decimal('5.0')),
            Candle(time=1, close=Decimal('10.0')),
            # Long. Size 10.
            Candle(time=2, close=Decimal('30.0')),
            Candle(time=3, close=Decimal('20.0')),
            # Short.
            Candle(time=4, close=Decimal('40.0')),
            # Long. Size 5.
            Candle(time=5, close=Decimal('10.0'))
        ]
    )
    informant = fakes.Informant(
        fees=Fees(Decimal('0.0'), Decimal('0.0')),
        filters=Filters(
            price=Price(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0')),
            size=Size(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0'))
        )
    )
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'start': 0,
        'end': 6,
        'quote': Decimal('100.0'),
        'analyze': False,
        'strategy_config': {
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0
        }
    }

    res = await Backtest(chandler=chandler, informant=informant).start(**agent_config)

    assert res.profit == -50
    assert res.potential_hodl_profit == 100
    assert res.duration == 6
    assert res.roi == Decimal('-0.5')
    assert res.annualized_roi == -1
    assert res.max_drawdown == Decimal('0.75')
    assert res.mean_drawdown == Decimal('0.25')
    assert res.mean_position_profit == -25
    assert res.mean_position_duration == 1
    assert res.start == 0
    assert res.end == 6


# 1. was failing as quote was incorrectly calculated after closing a position.
# 2. was failing as `juno.filters.Size.adjust` was rounding closest and not down.
@pytest.mark.parametrize('scenario_nr', [1, 2])
async def test_backtest_scenarios(scenario_nr):
    path = f'./data/backtest_scenario{scenario_nr}_candles.json'
    chandler = fakes.Chandler(
        # TODO: Load from JSON based on type.
        candles=list(map(lambda c: Candle(**c, closed=True), load_json_file(__file__, path)))
    )
    informant = fakes.Informant(
        fees=Fees(maker=Decimal('0.001'), taker=Decimal('0.001')),
        filters=Filters(
            price=Price(min=Decimal('0E-8'), max=Decimal('0E-8'), step=Decimal('0.00000100')),
            size=Size(
                min=Decimal('0.00100000'),
                max=Decimal('100000.00000000'),
                step=Decimal('0.00100000')
            )
        )
    )
    agent_config = {
        'exchange': 'binance',
        'symbol': 'eth-btc',
        'start': 1483225200000,
        'end': 1514761200000,
        'interval': HOUR_MS,
        'quote': Decimal('100.0'),
        'missed_candle_policy': MissedCandlePolicy.IGNORE,
        'analyze': False,
        'strategy_config': {
            'type': 'mamacx',
            'short_period': 18,
            'long_period': 29,
            'neg_threshold': Decimal('-0.25'),
            'pos_threshold': Decimal('0.25'),
            'persistence': 4
        }
    }

    assert await Backtest(chandler=chandler, informant=informant).start(**agent_config)


async def test_paper():
    chandler = fakes.Chandler(
        candles=[
            Candle(time=0, close=Decimal('5.0')),
            Candle(time=1, close=Decimal('10.0')),
            # 1. Long. Size 5 + 1.
            Candle(time=2, close=Decimal('30.0')),
            Candle(time=3, close=Decimal('20.0')),
            # 2. Short. Size 4 + 2.
        ]
    )
    informant = fakes.Informant()
    orderbook_data = {
        Side.BUY: {
            Decimal('10.0'): Decimal('5.0'),  # 1.
            Decimal('50.0'): Decimal('1.0'),  # 1.
        },
        Side.SELL: {
            Decimal('20.0'): Decimal('4.0'),  # 2.
            Decimal('10.0'): Decimal('2.0'),  # 2.
        }
    }
    orderbook = fakes.Orderbook(data={'dummy': {'eth-btc': orderbook_data}}, )
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'end': 4,
        'quote': Decimal('100.0'),
        'strategy_config': {
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0
        },
        'get_time_ms': fakes.Time(increment=1).get_time
    }

    assert await Paper(chandler=chandler, informant=informant, broker=broker).start(**agent_config)
    assert len(orderbook_data[Side.BUY]) == 0
    assert len(orderbook_data[Side.SELL]) == 0


async def test_live():
    chandler = fakes.Chandler(
        candles=[
            Candle(time=0, close=Decimal('5.0')),
            Candle(time=1, close=Decimal('10.0')),
            # 1. Long. Size 5 + 1.
            Candle(time=2, close=Decimal('30.0')),
            Candle(time=3, close=Decimal('20.0')),
            # 2. Short. Size 4 + 2.
        ]
    )
    informant = fakes.Informant()
    orderbook_data = {
        Side.BUY: {
            Decimal('10.0'): Decimal('5.0'),  # 1.
            Decimal('50.0'): Decimal('1.0'),  # 1.
        },
        Side.SELL: {
            Decimal('20.0'): Decimal('4.0'),  # 2.
            Decimal('10.0'): Decimal('2.0'),  # 2.
        }
    }
    orderbook = fakes.Orderbook(data={'dummy': {'eth-btc': orderbook_data}})
    wallet = fakes.Wallet({'dummy': {
        'btc': Balance(available=Decimal('100.0'), hold=Decimal('50.0')),
    }})
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'end': 4,
        'strategy_config': {
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0
        },
        'get_time_ms': fakes.Time(increment=1).get_time
    }

    assert await Live(chandler=chandler, informant=informant, wallet=wallet,
                      broker=broker).start(**agent_config)
    assert len(orderbook_data[Side.BUY]) == 0
    assert len(orderbook_data[Side.SELL]) == 0
