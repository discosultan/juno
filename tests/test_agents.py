# These tests act as integration tests among various components. Only exchange is mocked.

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import juno.assets
import juno.candles
from juno import Balance, Depth, Fill, OrderResult, OrderStatus
from juno.agents import Backtest, Live, Paper
from juno.assets import ExchangeInfo, Fees, Informant
from juno.asyncio import cancel, create_queue, resolved_stream, stream_queue
from juno.brokers import Market
from juno.candles import Candle, Chandler
from juno.components import Orderbook, User
from juno.exchanges import Exchange
from juno.filters import Filters, Price, Size
from juno.statistics import CoreStatistics
from juno.storages import Storage
from juno.time import HOUR_MS
from juno.traders import Basic, BasicState
from juno.trading import Position
from juno.typing import raw_to_type
from juno.utils import load_json_file

from . import fakes


async def test_backtest(storage: Storage) -> None:
    assets_exchange = MagicMock(spec=juno.assets.Exchange)
    assets_exchange.map_tickers.return_value = {}
    fees = Fees(Decimal('0.0'), Decimal('0.0'))
    filters = Filters(
        price=Price(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0')),
        size=Size(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0')),
    )
    assets_exchange.get_exchange_info.return_value = ExchangeInfo(
        fees={'__all__': fees},
        filters={'__all__': filters},
    )
    candles = [
        # Quote 100.
        Candle(time=0, close=Decimal('5.0')),
        Candle(time=1, close=Decimal('10.0')),
        # Long. Price 10. Size 10.
        Candle(time=2, close=Decimal('30.0')),
        Candle(time=3, close=Decimal('20.0')),
        # Liquidate. Price 20. Size 10. Quote 200.
        Candle(time=4, close=Decimal('40.0')),
        # Long. Price 40. Size 5.
        Candle(time=5, close=Decimal('10.0')),
        # Liquidate. Price 10. Size 5. Quote 50.
    ]
    candles_exchange = MagicMock(spec=juno.candles.Exchange)
    candles_exchange.map_candle_intervals.return_value = {1: 0}
    candles_exchange.stream_historical_candles.return_value = resolved_stream(*candles)

    config = Backtest.Config(
        exchange='magicmock',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('100.0'),
        strategy={
            'type': 'fixed',
            'advices': ['none', 'long', 'none', 'liquidate', 'long'],
        },
        trader={
            'type': 'basic',
            'symbol': 'eth-btc',
            'close_on_exit': True,
        },
    )
    informant = Informant(storage=storage, exchanges=[assets_exchange])
    chandler = Chandler(storage=storage, exchanges=[candles_exchange])
    trader = Basic(chandler, informant)
    agent = Backtest(traders=[trader], chandler=chandler)

    async with informant, chandler:
        res = await agent.run(config)

    assert res.summary

    stats = CoreStatistics.compose(res.summary)
    assert stats.profit == -50
    assert stats.duration == 6
    assert stats.roi == Decimal('-0.5')
    assert stats.annualized_roi == -1
    assert stats.max_drawdown == Decimal('0.75')
    assert stats.mean_drawdown == Decimal('0.375')
    assert stats.mean_position_profit == -25
    assert stats.mean_position_duration == 1
    assert stats.start == 0
    assert stats.end == 6

    assert CoreStatistics.calculate_hodl_profit(
        summary=res.summary, first_candle=candles[0], last_candle=candles[-1], fees=fees,
        filters=filters
    ) == 100


# 1. was failing as quote was incorrectly calculated after closing a position.
# 2. was failing as `juno.filters.Size.adjust` was rounding closest and not down.
@pytest.mark.parametrize('scenario_nr', [1, 2])
async def test_backtest_scenarios(scenario_nr: int, storage: Storage) -> None:
    assets_exchange = MagicMock(spec=juno.assets.Exchange)
    assets_exchange.map_tickers.return_value = {}
    assets_exchange.get_exchange_info.return_value = ExchangeInfo(
        fees={'__all__': Fees(maker=Decimal('0.001'), taker=Decimal('0.001'))},
        filters={'__all__': Filters(
            price=Price(min=Decimal('0E-8'), max=Decimal('0E-8'), step=Decimal('0.00000100')),
            size=Size(
                min=Decimal('0.00100000'),
                max=Decimal('100000.00000000'),
                step=Decimal('0.00100000'),
            )
        )},
    )
    candles_exchange = MagicMock(spec=juno.candles.Exchange)
    candles_exchange.map_candle_intervals.return_value = {HOUR_MS: 0}
    candles_exchange.stream_historical_candles.return_value = resolved_stream(*raw_to_type(
        load_json_file(__file__, f'./data/backtest_scenario{scenario_nr}_candles.json'),
        list[Candle],
    ))

    informant = Informant(storage=storage, exchanges=[assets_exchange])
    chandler = Chandler(storage=storage, exchanges=[candles_exchange])
    trader = Basic(chandler, informant)
    agent = Backtest(traders=[trader], chandler=chandler)

    config = Backtest.Config(
        exchange='magicmock',
        start=1483225200000,
        end=1514761200000,
        interval=HOUR_MS,
        quote=Decimal('100.0'),
        strategy={
            'type': 'doublema2',
            'short_period': 18,
            'long_period': 29,
            'neg_threshold': Decimal('-0.25'),
            'pos_threshold': Decimal('0.25'),
            'persistence': 4,
        },
        trader={
            'type': 'basic',
            'symbol': 'eth-btc',
            'missed_candle_policy': 'ignore',
        },
    )
    async with informant, chandler:
        await agent.run(config)


async def test_paper(storage: Storage) -> None:
    assets_exchange = MagicMock(juno.assets.Exchange)
    assets_exchange.map_tickers.return_value = {}
    assets_exchange.get_exchange_info.return_value = ExchangeInfo()

    exchange = MagicMock(Exchange)
    exchange.can_stream_depth_snapshot = False
    exchange.get_depth.return_value = Depth.Snapshot(
        bids=[
            (Decimal('10.0'), Decimal('5.0')),  # 1.
            (Decimal('50.0'), Decimal('1.0')),  # 1.
        ],
        asks=[
            (Decimal('20.0'), Decimal('4.0')),  # 2.
            (Decimal('10.0'), Decimal('2.0')),  # 2.
        ],
    )
    exchange.place_order.side_effect = [
        OrderResult(
            time=2,
            status=OrderStatus.FILLED,
            fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
        ),
        OrderResult(
            time=4,
            status=OrderStatus.FILLED,
            fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
        ),
    ]
    candles: asyncio.Queue[Candle] = asyncio.Queue()
    for candle in [
        Candle(time=0, close=Decimal('5.0')),
        Candle(time=1, close=Decimal('10.0')),
        # Long. Size 5 + 1.
        Candle(time=2, close=Decimal('30.0')),
        Candle(time=3, close=Decimal('20.0')),
        # Liquidate. Size 4 + 2.
    ]:
        candles.put_nowait(candle)
    candles_exchange = MagicMock(spec=juno.candles.Exchange)
    candles_exchange.map_candle_intervals.return_value = {1: 0}
    candles_exchange.connect_stream_candles.return_value.__aenter__.return_value = stream_queue(
        candles
    )

    informant = Informant(storage=storage, exchanges=[assets_exchange])
    chandler = Chandler(storage=storage, exchanges=[candles_exchange])
    orderbook = Orderbook(exchanges=[exchange])
    user = User(exchanges=[exchange])
    broker = Market(informant=informant, orderbook=orderbook, user=user)
    trader = Basic(chandler=chandler, informant=informant, broker=broker)
    agent = Paper(traders=[trader], informant=informant)

    config = Paper.Config(
        exchange='magicmock',
        interval=1,
        quote=Decimal('100.0'),
        strategy={
            'type': 'fixed',
            'advices': ['none', 'long', 'none', 'liquidate'],
        },
        trader={
            'type': 'basic',
            'symbol': 'eth-btc',
        },
    )
    async with informant, chandler:
        task = asyncio.create_task(agent.run(config))
        await asyncio.wait_for(candles.join(), 1)
        await cancel(task)

    summary = task.result().summary
    assert summary
    long_positions = summary.list_positions(type_=Position.Long)
    assert len(long_positions) == 1
    pos = long_positions[0]
    assert Fill.total_size(pos.open_fills) == 6
    assert Fill.total_size(pos.close_fills) == 6
    assert pos.profit == 0


async def test_live(storage: Storage) -> None:
    assets_exchange = MagicMock(juno.assets.Exchange)
    assets_exchange.map_tickers.return_value = {}
    assets_exchange.get_exchange_info.return_value = ExchangeInfo()
    exchange = MagicMock(spec=Exchange)
    exchange.map_balances.return_value = {
        'spot': {'btc': Balance(available=Decimal('100.0'), hold=Decimal('50.0'))}
    }
    exchange.place_order.side_effect = [
        OrderResult(
            time=2,
            status=OrderStatus.FILLED,
            fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
        ),
        OrderResult(
            time=4,
            status=OrderStatus.FILLED,
            fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
        ),
    ]
    candles = create_queue([
        Candle(time=0, close=Decimal('5.0')),
        Candle(time=1, close=Decimal('10.0')),
        # Long. Size 5 + 1.
        Candle(time=2, close=Decimal('30.0')),
        Candle(time=3, close=Decimal('20.0')),
        # Liquidate. Size 4 + 2.
    ])
    candles_exchange = MagicMock(spec=juno.candles.Exchange)
    candles_exchange.map_candle_intervals.return_value = {1: 0}
    candles_exchange.connect_stream_candles.return_value.__aenter__.return_value = stream_queue(
        candles
    )

    informant = Informant(storage=storage, exchanges=[assets_exchange])
    chandler = Chandler(storage=storage, exchanges=[candles_exchange])
    orderbook = Orderbook(exchanges=[exchange])
    user = User(exchanges=[exchange])
    broker = Market(informant=informant, orderbook=orderbook, user=user)
    trader = Basic(chandler=chandler, informant=informant, broker=broker, user=user)
    agent = Live(traders=[trader], informant=informant, storage=storage)

    config = Live.Config(
        exchange='magicmock',
        interval=1,
        strategy={
            'type': 'fixed',
            'advices': ['none', 'long', 'none', 'liquidate'],
        },
        trader={
            'type': 'basic',
            'symbol': 'eth-btc',
        },
    )
    async with informant, chandler:
        task = asyncio.create_task(agent.run(config))
        await asyncio.wait_for(candles.join(), 1)
        await cancel(task)

    summary = task.result().summary
    assert summary
    long_positions = summary.list_positions(type_=Position.Long)
    assert len(long_positions) == 1
    pos = long_positions[0]
    assert pos.open_time == 2
    assert pos.close_time == 4


@pytest.mark.parametrize('strategy', ['fixed', 'fourweekrule'])
async def test_live_persist_and_resume(strategy: str, storage: Storage) -> None:
    assets_exchange = MagicMock(juno.assets.Exchange)
    assets_exchange.map_tickers.return_value = {}
    assets_exchange.get_exchange_info.return_value = ExchangeInfo()
    exchange = MagicMock(spec=Exchange)
    exchange.map_balances.return_value = {'spot': {'btc': Balance(available=Decimal('1.0'))}}
    candles = create_queue([Candle(time=0, close=Decimal('1.0'))])
    candles_exchange = MagicMock(spec=juno.candles.Exchange)
    candles_exchange.map_candle_intervals.return_value = {1: 0}
    candles_exchange.connect_stream_candles.return_value.__aenter__.return_value = stream_queue(
        candles
    )

    informant = Informant(storage=storage, exchanges=[assets_exchange])
    chandler = Chandler(storage=storage, exchanges=[candles_exchange])
    orderbook = Orderbook(exchanges=[exchange])
    user = User(exchanges=[exchange])
    broker = Market(informant=informant, orderbook=orderbook, user=user)
    trader = Basic(chandler=chandler, informant=informant, broker=broker, user=user)
    agent = Live(
        traders=[trader],
        informant=informant,
        storage=storage,
        get_time_ms=fakes.Time(time=0).get_time,
    )

    config = Live.Config(
        name='name',
        persist=True,
        exchange='magicmock',
        interval=1,
        strategy={'type': strategy},
        trader={
            'type': 'basic',
            'symbol': 'eth-btc',
        },
    )
    async with informant, chandler:
        agent_run_task = asyncio.create_task(agent.run(config))
        await asyncio.wait_for(candles.join(), 1)
        await cancel(agent_run_task)

        candles.put_nowait(Candle(time=1, close=Decimal('1.0')))
        candles_exchange.connect_stream_candles.return_value.__aenter__.return_value = (
            stream_queue(candles)
        )
        agent_run_task = asyncio.create_task(agent.run(config))
        await asyncio.wait_for(candles.join(), 1)
        await cancel(agent_run_task)

    state: BasicState = agent_run_task.result()
    assert state.first_candle
    assert state.first_candle.time == 0
    assert state.last_candle
    assert state.last_candle.time == 1
