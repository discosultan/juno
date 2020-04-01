import asyncio
from decimal import Decimal
from typing import Any, List

import pytest

from juno import Balance, Candle, Fees, Side
from juno.agents import Backtest, Live, Paper
from juno.asyncio import cancel
from juno.filters import Filters, Price, Size
from juno.storages import Storage
from juno.time import HOUR_MS
from juno.trading import MissedCandlePolicy, Trader
from juno.typing import raw_to_type
from juno.utils import load_json_file

from . import fakes


async def test_backtest() -> None:
    candles = [
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
    chandler = fakes.Chandler(candles={('dummy', 'eth-btc', 1): candles})
    fees = Fees(Decimal('0.0'), Decimal('0.0'))
    filters = Filters(
        price=Price(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0')),
        size=Size(min=Decimal('1.0'), max=Decimal('10000.0'), step=Decimal('1.0'))
    )
    informant = fakes.Informant(fees=fees, filters=filters)
    trader = Trader(chandler=chandler, informant=informant)
    config = Backtest.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('100.0'),
        strategy={
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0
        }
    )

    res: Trader.State[Any] = await Backtest(trader=trader).run(config)

    summary = res.summary
    assert summary
    assert summary.profit == -50
    assert summary.duration == 6
    assert summary.roi == Decimal('-0.5')
    assert summary.annualized_roi == -1
    assert summary.max_drawdown == Decimal('0.75')
    assert summary.mean_drawdown == Decimal('0.25')
    assert summary.mean_position_profit == -25
    assert summary.mean_position_duration == 1
    assert summary.start == 0
    assert summary.end == 6
    assert summary.calculate_hodl_profit(candles[0], candles[-1], fees, filters) == 100


# 1. was failing as quote was incorrectly calculated after closing a position.
# 2. was failing as `juno.filters.Size.adjust` was rounding closest and not down.
@pytest.mark.parametrize('scenario_nr', [1, 2])
async def test_backtest_scenarios(scenario_nr: int) -> None:
    chandler = fakes.Chandler(candles={('binance', 'eth-btc', HOUR_MS): raw_to_type(
        load_json_file(__file__, f'./data/backtest_scenario{scenario_nr}_candles.json'),
        List[Candle]
    )})
    informant = fakes.Informant(
        fees=Fees(maker=Decimal('0.001'), taker=Decimal('0.001')),
        filters=Filters(
            price=Price(min=Decimal('0E-8'), max=Decimal('0E-8'), step=Decimal('0.00000100')),
            size=Size(
                min=Decimal('0.00100000'),
                max=Decimal('100000.00000000'),
                step=Decimal('0.00100000'),
            )
        )
    )
    trader = Trader(chandler=chandler, informant=informant)
    config = Backtest.Config(
        exchange='binance',
        symbol='eth-btc',
        start=1483225200000,
        end=1514761200000,
        interval=HOUR_MS,
        quote=Decimal('100.0'),
        missed_candle_policy=MissedCandlePolicy.IGNORE,
        strategy={
            'type': 'mamacx',
            'short_period': 18,
            'long_period': 29,
            'neg_threshold': Decimal('-0.25'),
            'pos_threshold': Decimal('0.25'),
            'persistence': 4,
        },
    )

    await Backtest(trader=trader).run(config)


async def test_paper() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('5.0')),
            Candle(time=1, close=Decimal('10.0')),
            # 1. Long. Size 5 + 1.
            Candle(time=2, close=Decimal('30.0')),
            Candle(time=3, close=Decimal('20.0')),
            # 2. Short. Size 4 + 2.
        ]
    })
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
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    trader = Trader(chandler=chandler, informant=informant, broker=broker)
    config = Paper.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        end=4,
        quote=Decimal('100.0'),
        strategy={
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0,
        },
    )

    await Paper(
        informant=informant, trader=trader, get_time_ms=fakes.Time(increment=1).get_time,
    ).run(config)
    assert len(orderbook_data[Side.BUY]) == 0
    assert len(orderbook_data[Side.SELL]) == 0


async def test_live(storage: Storage) -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('5.0')),
            Candle(time=1, close=Decimal('10.0')),
            # 1. Long. Size 5 + 1.
            Candle(time=2, close=Decimal('30.0')),
            Candle(time=3, close=Decimal('20.0')),
            # 2. Short. Size 4 + 2.
        ]
    })
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
    trader = Trader(chandler=chandler, informant=informant, broker=broker)
    config = Live.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        end=4,
        strategy={
            'type': 'mamacx',
            'short_period': 1,
            'long_period': 2,
            'neg_threshold': Decimal('-1.0'),
            'pos_threshold': Decimal('1.0'),
            'persistence': 0,
        },
    )

    await Live(
        informant=informant, wallet=wallet, trader=trader, storage=storage,
        get_time_ms=fakes.Time(increment=1).get_time,
    ).run(config)
    assert len(orderbook_data[Side.BUY]) == 0
    assert len(orderbook_data[Side.SELL]) == 0


@pytest.mark.parametrize('strategy', ['fixed', 'fourweekrule'])
async def test_live_persist_and_resume(storage: Storage, strategy: str) -> None:
    candle_key = ('dummy', 'eth-btc', 1)
    chandler = fakes.Chandler(
        candles={candle_key: []},
        future_candles={candle_key: [Candle(time=0, close=Decimal('1.0'))]},
    )
    informant = fakes.Informant()
    orderbook = fakes.Orderbook()
    wallet = fakes.Wallet({'dummy': {
        'btc': Balance(available=Decimal('1.0')),
    }})
    broker = fakes.Market(informant, orderbook, update_orderbook=True)
    trader = Trader(chandler=chandler, informant=informant, broker=broker)
    config = Live.Config(
        name='name',
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        end=2,
        strategy={'type': strategy},
    )
    live = Live(
        informant=informant, wallet=wallet, trader=trader, storage=storage,
        get_time_ms=fakes.Time(increment=1).get_time,
    )

    agent_run_task = asyncio.create_task(live.run(config))
    await chandler.future_candle_queues[candle_key].join()
    await cancel(agent_run_task)

    chandler.future_candle_queues[candle_key].put_nowait(
        Candle(time=1, close=Decimal('1.0'))
    )
    await live.run(config)
