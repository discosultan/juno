from decimal import Decimal

import pytest

from juno import Balance, Candle, Fees, Side
from juno.agents import Backtest, Live, Paper
from juno.filters import Filters, Price, Size
from juno.time import HOUR_MS
from juno.utils import load_json_file

from . import fakes
from .utils import new_candle


async def test_backtest(loop):
    informant = fakes.Informant(
        fees=Fees(Decimal(0), Decimal(0)),
        filters=Filters(
            price=Price(min=Decimal(1), max=Decimal(10000), step=Decimal(1)),
            size=Size(min=Decimal(1), max=Decimal(10000), step=Decimal(1))
        ),
        candles=[
            new_candle(time=0, close=Decimal(5)),
            new_candle(time=1, close=Decimal(10)),
            # Long. Size 10.
            new_candle(time=2, close=Decimal(30)),
            new_candle(time=3, close=Decimal(20)),
            # Short.
            new_candle(time=4, close=Decimal(40)),
            # Long. Size 5.
            new_candle(time=5, close=Decimal(10))
        ]
    )
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'start': 0,
        'end': 6,
        'quote': Decimal(100),
        'strategy_config': {
            'name': 'emaemacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal(-1),
            'pos_threshold': Decimal(1),
            'persistence': 0
        }
    }

    res = await Backtest(informant=informant).start(**agent_config)

    assert res.profit == -50
    assert res.potential_hodl_profit == 100
    assert res.duration == 6
    assert res.roi == Decimal('-0.5')
    assert res.annualized_roi == Decimal(-1)
    assert res.max_drawdown == Decimal('0.75')
    assert res.mean_drawdown == Decimal('0.25')
    assert res.mean_position_profit == -25
    assert res.mean_position_duration == 1
    assert res.start == 0
    assert res.end == 6


# 1. was failing as quote was incorrectly calculated after closing a position.
# 2. was failing as `juno.filters.Size.adjust` was rounding closest and not down.
@pytest.mark.parametrize('scenario_nr', [1, 2])
async def test_backtest_scenarios(loop, scenario_nr):
    path = f'./data/backtest_scenario{scenario_nr}_candles.json'
    informant = fakes.Informant(
        fees=Fees(maker=Decimal('0.001'), taker=Decimal('0.001')),
        filters=Filters(
            price=Price(min=Decimal('0E-8'), max=Decimal('0E-8'), step=Decimal('0.00000100')),
            size=Size(
                min=Decimal('0.00100000'),
                max=Decimal('100000.00000000'),
                step=Decimal('0.00100000')
            )
        ),
        candles=list(map(lambda c: Candle(**c, closed=True), load_json_file(__file__, path)))
    )
    agent_config = {
        'name': 'backtest',
        'exchange': 'binance',
        'symbol': 'eth-btc',
        'start': 1483225200000,
        'end': 1514761200000,
        'interval': HOUR_MS,
        'quote': Decimal(100),
        'restart_on_missed_candle': False,
        'strategy_config': {
            'name': 'emaemacx',
            'short_period': 18,
            'long_period': 29,
            'neg_threshold': Decimal('-0.25'),
            'pos_threshold': Decimal('0.25'),
            'persistence': 4
        }
    }

    assert await Backtest(informant=informant).start(**agent_config)


async def test_paper(loop):
    informant = fakes.Informant(
        fees=Fees.none(),
        filters=Filters.none(),
        candles=[
            new_candle(time=0, close=Decimal(5)),
            new_candle(time=1, close=Decimal(10)),
            # 1. Long. Size 5 + 1.
            new_candle(time=2, close=Decimal(30)),
            new_candle(time=3, close=Decimal(20)),
            # 2. Short. Size 4 + 2.
        ]
    )
    orderbook_data = {
        Side.BID: {
            Decimal(10): Decimal(5),  # 1.
            Decimal(50): Decimal(1),  # 1.
        },
        Side.ASK: {
            Decimal(20): Decimal(4),  # 2.
            Decimal(10): Decimal(2),  # 2.
        }
    }
    orderbook = fakes.Orderbook(data={'dummy': {'eth-btc': orderbook_data}}, )
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'end': 4,
        'quote': Decimal(100),
        'strategy_config': {
            'name': 'emaemacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal(-1),
            'pos_threshold': Decimal(1),
            'persistence': 0
        },
        'get_time': fakes.Time()
    }

    assert await Paper(informant=informant, broker=broker).start(**agent_config)
    assert len(orderbook_data[Side.BID]) == 0
    assert len(orderbook_data[Side.ASK]) == 0


async def test_live(loop):
    informant = fakes.Informant(
        fees=Fees.none(),
        filters=Filters.none(),
        candles=[
            new_candle(time=0, close=Decimal(5)),
            new_candle(time=1, close=Decimal(10)),
            # 1. Long. Size 5 + 1.
            new_candle(time=2, close=Decimal(30)),
            new_candle(time=3, close=Decimal(20)),
            # 2. Short. Size 4 + 2.
        ]
    )
    orderbook_data = {
        Side.BID: {
            Decimal(10): Decimal(5),  # 1.
            Decimal(50): Decimal(1),  # 1.
        },
        Side.ASK: {
            Decimal(20): Decimal(4),  # 2.
            Decimal(10): Decimal(2),  # 2.
        }
    }
    orderbook = fakes.Orderbook(data={'dummy': {'eth-btc': orderbook_data}})
    wallet = fakes.Wallet({'dummy': {'btc': Balance(available=Decimal(100), hold=Decimal(50))}})
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    agent_config = {
        'exchange': 'dummy',
        'symbol': 'eth-btc',
        'interval': 1,
        'end': 4,
        'strategy_config': {
            'name': 'emaemacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal(-1),
            'pos_threshold': Decimal(1),
            'persistence': 0
        },
        'get_time': fakes.Time()
    }

    assert await Live(informant=informant, wallet=wallet, broker=broker).start(**agent_config)
    assert len(orderbook_data[Side.BID]) == 0
    assert len(orderbook_data[Side.ASK]) == 0
