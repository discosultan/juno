from decimal import Decimal

import pytest

from juno import Candle, Fees, SymbolInfo, Fill, Fills
from juno.agents import Agent, Backtest, Paper, list_required_component_names
from juno.agents.summary import Position
from juno.components import Orderbook
from juno.time import HOUR_MS

from .utils import load_json_file


async def test_backtest(loop):
    informant = FakeInformant(
        fees=Fees(Decimal(0), Decimal(0)),
        symbol_info=SymbolInfo(
            min_size=Decimal(1), max_size=Decimal(10000), size_step=Decimal(1),
            min_price=Decimal(1), max_price=Decimal(10000), price_step=Decimal(1)),
        candles=[
            Candle(0, Decimal(1), Decimal(1), Decimal(1), Decimal(5), Decimal(1)),
            Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(10), Decimal(1)),
            # Long. Size 10.
            Candle(2, Decimal(1), Decimal(1), Decimal(1), Decimal(30), Decimal(1)),
            Candle(3, Decimal(1), Decimal(1), Decimal(1), Decimal(20), Decimal(1)),
            # Short.
            Candle(4, Decimal(1), Decimal(1), Decimal(1), Decimal(40), Decimal(1)),
            # Long. Size 5.
            Candle(5, Decimal(1), Decimal(1), Decimal(1), Decimal(10), Decimal(1))
        ])
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

    async with Backtest(components={'informant': informant}, agent_config=agent_config) as agent:
        res = await agent.start()

    assert res.profit == -50
    assert res.potential_hodl_profit == 100
    assert res.duration == 6
    assert res.yearly_roi == -2629746000
    assert res.max_drawdown == Decimal('0.75')
    assert res.mean_drawdown == Decimal('0.25')
    assert res.mean_position_profit == -25
    assert res.mean_position_duration == 1
    assert res.start == 0
    assert res.end == 6


# 1. was failing as quote was incorrectly calculated after closing a position.
# 2. was failing as `juno.math.adjust_size` was rounding closest and not down.
@pytest.mark.parametrize('scenario_nr', [1, 2])
async def test_backtest_scenarios(loop, scenario_nr):
    path = f'/data/backtest_scenario{scenario_nr}_candles.json'
    informant = FakeInformant(
        fees=Fees(maker=Decimal('0.001'), taker=Decimal('0.001')),
        symbol_info=SymbolInfo(
            min_size=Decimal('0.00100000'),
            max_size=Decimal('100000.00000000'),
            size_step=Decimal('0.00100000'),
            min_price=Decimal('0E-8'),
            max_price=Decimal('0E-8'),
            price_step=Decimal('0.00000100')),
        candles=list(map(lambda c: Candle(**c), load_json_file(path)))
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

    async with Backtest(components={'informant': informant}, agent_config=agent_config) as agent:
        await agent.start()


async def test_paper(loop):
    informant = FakeInformant(
        fees=Fees(Decimal(0), Decimal(0)),
        symbol_info=SymbolInfo(
            min_size=Decimal(1), max_size=Decimal(10000), size_step=Decimal(1),
            min_price=Decimal(1), max_price=Decimal(10000), price_step=Decimal(1)),
        candles=[
            Candle(0, Decimal(1), Decimal(1), Decimal(1), Decimal(5), Decimal(1)),
            Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(10), Decimal(1)),
            # 1. Long. Size 5 + 1.
            Candle(2, Decimal(1), Decimal(1), Decimal(1), Decimal(30), Decimal(1)),
            Candle(3, Decimal(1), Decimal(1), Decimal(1), Decimal(20), Decimal(1)),
            # 2. Short. Size 4 + 2.
        ])
    orderbook_data = {
        'asks': {
            Decimal(10): Decimal(5),  # 1.
            Decimal(50): Decimal(1),  # 1.
        },
        'bids': {
            Decimal(20): Decimal(4),  # 2.
            Decimal(10): Decimal(2),  # 2.
        }
    }
    orderbook = FakeOrderbook({
        'dummy': {
            'eth-btc': orderbook_data
        }
    }, update_on_find=True)
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
        'get_time': FakeTime()
    }

    async with Paper(components={'informant': informant, 'orderbook': orderbook},
                     agent_config=agent_config) as agent:
        res = await agent.start()

    assert res
    assert len(orderbook_data['asks']) == 0
    assert len(orderbook_data['bids']) == 0


def test_position():
    pos = Position(
        time=0,
        fills=Fills([
            Fill(price=Decimal(2), size=Decimal(6), fee=Decimal(2), fee_asset='btc')
        ]))
    pos.close(
        time=1,
        fills=Fills([
            Fill(price=Decimal(2), size=Decimal(2), fee=Decimal(1), fee_asset='eth')
        ]))

    assert pos.cost == Decimal(12)  # 6 * 2
    assert pos.gain == Decimal(3)  # 2 * 2 - 1
    assert pos.dust == Decimal(2)  # 6 - 2 - 2
    assert pos.profit == Decimal(-9)
    assert pos.duration == 1
    assert pos.start == 0
    assert pos.end == 1
    # TODO: assert roi and yearly roi


def test_list_required_component_names():

    class Foo(Agent):
        required_components = ['a']

    class Bar(Agent):
        required_components = ['b', 'c']

    result = list_required_component_names(
        config={
            'agents': [
                {'name': 'foo'},
                {'name': 'bar'}
            ]},
        agents={
            'foo': Foo,
            'bar': Bar
        })

    assert result == set(('a', 'b', 'c'))


class FakeInformant:

    def __init__(self, fees, symbol_info, candles):
        self.fees = fees
        self.symbol_info = symbol_info
        self.candles = candles

    def get_fees(self, exchanges):
        return self.fees

    def get_symbol_info(self, exchange, symbol):
        return self.symbol_info

    async def stream_candles(self, exchange, symbol, interval, start, end):
        for candle in self.candles:
            yield candle, True


class FakeOrderbook(Orderbook):

    def __init__(self, orderbooks, update_on_find=False):
        self._orderbooks = orderbooks
        self._update_on_find = update_on_find

    def find_market_order_asks(self, exchange, symbol, quote_balance, symbol_info, fees):
        asks = super().find_market_order_asks(exchange, symbol, quote_balance, symbol_info, fees)
        if self._update_on_find:
            self._remove_from_side(self._orderbooks[exchange][symbol]['asks'], asks)
        return asks

    def find_market_order_bids(self, exchange, symbol, base_balance, symbol_info, fees):
        bids = super().find_market_order_bids(exchange, symbol, base_balance, symbol_info, fees)
        if self._update_on_find:
            self._remove_from_side(self._orderbooks[exchange][symbol]['bids'], bids)
        return bids

    def _remove_from_side(self, side, fills):
        for fill in fills:
            side[fill.price] -= fill.size
            if side[fill.price] == Decimal(0):
                del side[fill.price]


def FakeTime():
    time = -1

    def get_time():
        nonlocal time
        time += 1
        return time

    return get_time
