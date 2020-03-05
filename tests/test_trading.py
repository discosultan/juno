from decimal import Decimal
from typing import Any, List, Tuple

import pytest

from juno import Advice, Candle, Fill
from juno.trading import MissedCandlePolicy, Position, Trader, TradingSummary

from . import fakes


def test_position() -> None:
    pos = Position(
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(price=Decimal('2.0'), size=Decimal('6.0'), fee=Decimal('2.0'), fee_asset='btc')
        ]
    )
    pos.close(
        time=1,
        fills=[
            Fill(price=Decimal('2.0'), size=Decimal('2.0'), fee=Decimal('1.0'), fee_asset='eth')
        ]
    )

    assert pos.cost == 12  # 6 * 2
    assert pos.gain == 3  # 2 * 2 - 1
    assert pos.dust == 2  # 6 - 2 - 2
    assert pos.profit == -9
    assert pos.duration == 1
    assert pos.start == 0
    assert pos.end == 1
    assert pos.roi == Decimal('-0.75')
    assert pos.annualized_roi == -1


def test_position_annualized_roi_overflow() -> None:
    pos = Position(
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(price=Decimal('1.0'), size=Decimal('1.0'), fee=Decimal('0.0'), fee_asset='eth')
        ]
    )
    pos.close(
        time=2,
        fills=[
            Fill(price=Decimal('2.0'), size=Decimal('1.0'), fee=Decimal('0.0'), fee_asset='btc')
        ]
    )

    assert pos.annualized_roi == Decimal('Inf')


def test_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'))
    # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
    # Series: 100, 110, 99, 103.95, 93.55, 102.91
    positions = [
        new_closed_position(Decimal('10.0')),
        new_closed_position(Decimal('-11.0')),
        new_closed_position(Decimal('4.95')),
        new_closed_position(Decimal('-10.4')),
        new_closed_position(Decimal('9.36')),
    ]
    for position in positions:
        summary.append_position(position)

    assert summary.cost == Decimal('100.0')
    assert summary.gain == Decimal('102.91')
    assert summary.profit == Decimal('2.91')
    assert summary.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'))
    assert summary.cost == 100
    assert summary.gain == 100
    assert summary.profit == 0
    assert summary.max_drawdown == 0


async def test_trader_trailing_stop_loss() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('10.0')),  # Buy.
            Candle(time=1, close=Decimal('20.0')),
            Candle(time=2, close=Decimal('18.0')),  # Trigger trailing stop (10%).
            Candle(time=3, close=Decimal('10.0')),  # Sell (do not act).
        ]
    })
    trader = Trader(chandler=chandler, informant=fakes.Informant())

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('10.0'),
        strategy_module='tests.fakes',
        strategy='strategy',
        strategy_kwargs={'advices': [Advice.BUY, None, None, Advice.SELL]},
        trailing_stop=Decimal('0.1'),
    )
    state: Trader.State[Any] = Trader.State()
    await trader.run(config, state)
    assert state.summary

    assert state.summary.profit == 8


async def test_trader_restart_on_missed_candle() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0),
            Candle(time=1),
            # 1 candle skipped.
            Candle(time=3),  # Trigger restart.
            Candle(time=4),
            Candle(time=5),
        ]
    })
    trader = Trader(chandler=chandler, informant=fakes.Informant())
    updates: List[Tuple[int, Candle]] = []

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('10.0'),
        strategy_module='tests.fakes',
        strategy='strategy',
        strategy_kwargs={'advices': [None, None, None], 'updates': updates},
        missed_candle_policy=MissedCandlePolicy.RESTART,
    )
    state: Trader.State[Any] = Trader.State()
    await trader.run(config, state)

    assert len(updates) == 5

    ids = [id_ for id_, _ in updates]
    id1 = ids[0]
    id2 = ids[2]
    assert id1 != id2
    assert all(id_ == id1 for id_ in ids[:2])
    assert all(id_ == id2 for id_ in ids[2:])

    candle_times = [c.time for _, c in updates]
    assert candle_times[0] == 0
    assert candle_times[1] == 1
    assert candle_times[2] == 3
    assert candle_times[3] == 4
    assert candle_times[4] == 5


async def test_trader_assume_same_as_last_on_missed_candle() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0),
            Candle(time=1),
            # 2 candles skipped.
            Candle(time=4),  # Generate new candles with previous data.
        ]
    })
    trader = Trader(chandler=chandler, informant=fakes.Informant())
    updates: List[Tuple[int, Candle]] = []

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=5,
        quote=Decimal('10.0'),
        strategy_module='tests.fakes',
        strategy='strategy',
        strategy_kwargs={'advices': [None, None, None, None, None], 'updates': updates},
        missed_candle_policy=MissedCandlePolicy.LAST,
    )
    state: Trader.State[Any] = Trader.State()
    await trader.run(config, state)

    candle_times = [c.time for _, c in updates]
    assert len(candle_times) == 5
    assert candle_times[0] == 0
    assert candle_times[1] == 1
    assert candle_times[2] == 2
    assert candle_times[3] == 3
    assert candle_times[4] == 4


def new_closed_position(profit):
    size = abs(profit)
    price = Decimal('1.0') if profit >= 0 else Decimal('-1.0')
    pos = Position(
        symbol='eth-btc',
        time=0,
        fills=[Fill(price=Decimal('0.0'), size=size)]
    )
    pos.close(time=1, fills=[Fill(price=price, size=size)])
    return pos
