import asyncio
from decimal import Decimal
from typing import cast

import pytest

from juno import BorrowInfo, Candle, Fill, Filters, Ticker, strategies
from juno.asyncio import cancel
from juno.trading import MissedCandlePolicy, MultiTrader, Position, Trader, TradingSummary

from . import fakes


def test_long_position() -> None:
    open_pos = Position.OpenLong(
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('6.0'), quote=Decimal('12.0'),
                fee=Decimal('2.0'), fee_asset='eth'
            )
        ],
    )
    pos = open_pos.close(
        time=1,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('2.0'), quote=Decimal('4.0'),
                fee=Decimal('1.0'), fee_asset='btc'
            )
        ],
    )

    assert pos.cost == 12  # 6 * 2
    assert pos.gain == 3  # 2 * 2 - 1
    assert pos.dust == 2  # 6 - 2 - 2
    assert pos.profit == -9
    assert pos.duration == 1
    assert pos.open_time == 0
    assert pos.close_time == 1
    assert pos.roi == Decimal('-0.75')
    assert pos.annualized_roi == -1


def test_long_position_annualized_roi_overflow() -> None:
    open_pos = Position.OpenLong(
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(
                price=Decimal('1.0'), size=Decimal('1.0'), quote=Decimal('1.0'),
                fee=Decimal('0.0'), fee_asset='eth'
            )
        ],
    )
    pos = open_pos.close(
        time=2,
        fills=[
            Fill(
                price=Decimal('2.0'), size=Decimal('1.0'), quote=Decimal('2.0'),
                fee=Decimal('0.0'), fee_asset='btc'
            )
        ],
    )

    assert pos.annualized_roi == Decimal('Inf')


def test_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'), quote_asset='btc')
    # Data based on: https://www.quantshare.com/sa-92-the-average-maximum-drawdown-metric
    # Series: 100, 110, 99, 103.95, 93.55, 102.91
    positions = [
        new_closed_long_position(Decimal('10.0')),
        new_closed_long_position(Decimal('-11.0')),
        new_closed_long_position(Decimal('4.95')),
        new_closed_long_position(Decimal('-10.4')),
        new_closed_long_position(Decimal('9.36')),
    ]
    for position in positions:
        summary.append_position(position)

    assert summary.cost == Decimal('100.0')
    assert summary.gain == Decimal('102.91')
    assert summary.profit == Decimal('2.91')
    assert summary.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_trading_summary() -> None:
    summary = TradingSummary(start=0, quote=Decimal('100.0'), quote_asset='btc')
    assert summary.cost == 100
    assert summary.gain == 100
    assert summary.profit == 0
    assert summary.max_drawdown == 0


async def test_trader_upside_trailing_stop() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('10.0')),  # Open long.
            Candle(time=1, close=Decimal('20.0')),
            Candle(time=2, close=Decimal('18.0')),  # Trigger trailing stop (10%).
            Candle(time=3, close=Decimal('10.0')),  # Close long (do not act).
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
        strategy='fixed',
        strategy_kwargs={
            'advices': ['long', 'long', 'long', 'liquidate'],
            'ignore_mid_trend': False,
        },
        trailing_stop=Decimal('0.1'),
        long=True,
        short=False,
    )
    summary = await trader.run(config)

    assert summary.profit == 8


async def test_trader_downside_trailing_stop() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('10.0')),  # Open short.
            Candle(time=1, close=Decimal('5.0')),
            Candle(time=2, close=Decimal('6.0')),  # Trigger trailing stop (10%).
            Candle(time=3, close=Decimal('10.0')),  # Close short (do not act).
        ]
    })
    informant = fakes.Informant(
        filters=Filters(is_margin_trading_allowed=True),
        borrow_info=BorrowInfo(limit=Decimal('1.0')),
        margin_multiplier=2,
    )
    trader = Trader(chandler=chandler, informant=informant)

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('10.0'),
        strategy='fixed',
        strategy_kwargs={
            'advices': ['short', 'short', 'short', 'liquidate'],
            'ignore_mid_trend': False,
        },
        trailing_stop=Decimal('0.1'),
        long=False,
        short=True,
    )
    summary = await trader.run(config)

    assert summary.profit == 4


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

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('10.0'),
        strategy='fixed',
        strategy_kwargs={'advices': ['none'] * 3},
        missed_candle_policy=MissedCandlePolicy.RESTART,
    )
    initial_strategy = cast(strategies.Fixed, config.new_strategy())
    state = Trader.State(strategy=initial_strategy)
    await trader.run(config, state)

    assert state.strategy != initial_strategy

    updates = initial_strategy.updates + cast(strategies.Fixed, state.strategy).updates
    assert len(updates) == 5

    candle_times = [c.time for c in updates]
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

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=5,
        quote=Decimal('10.0'),
        strategy='fixed',
        strategy_kwargs={'advices': ['none'] * 5},
        missed_candle_policy=MissedCandlePolicy.LAST,
    )
    state = Trader.State()
    await trader.run(config, state)

    assert state.strategy

    candle_times = [c.time for c in state.strategy.updates]  # type: ignore
    assert len(candle_times) == 5
    assert candle_times[0] == 0
    assert candle_times[1] == 1
    assert candle_times[2] == 2
    assert candle_times[3] == 3
    assert candle_times[4] == 4


async def test_trader_adjust_start_ignore_mid_trend() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
            Candle(time=2, close=Decimal('1.0')),
            Candle(time=3, close=Decimal('1.0')),
        ]
    })
    trader = Trader(chandler=chandler, informant=fakes.Informant())
    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=2,
        end=4,
        quote=Decimal('1.0'),
        strategy='fixed',
        strategy_kwargs={
            'advices': ['none', 'long', 'long', 'none'],
            'maturity': 1,
            'ignore_mid_trend': True,
            'persistence': 1,
        },
        adjust_start=True,
    )

    summary = await trader.run(config)

    assert summary.num_positions == 0


async def test_trader_adjust_start_persistence() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
            Candle(time=2, close=Decimal('1.0')),
            Candle(time=3, close=Decimal('1.0')),
        ]
    })
    trader = Trader(chandler=chandler, informant=fakes.Informant())
    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=3,
        end=4,
        quote=Decimal('1.0'),
        strategy='fixed',
        strategy_kwargs={
            'advices': ['none', 'long', 'long', 'long'],
            'maturity': 1,
            'ignore_mid_trend': False,
            'persistence': 2,
        },
        adjust_start=True,
    )

    summary = await trader.run(config)

    assert summary.num_positions == 1
    assert summary.num_long_positions == 1


async def test_trader_persist_and_resume(storage: fakes.Storage) -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', 'eth-btc', 1):
            [
                Candle(time=0),
                Candle(time=1),
                Candle(time=2),
                Candle(time=3),
            ]
        },
        future_candles={
            ('dummy', 'eth-btc', 1):
            [
                Candle(time=4),
            ]
        }
    )
    trader = Trader(chandler=chandler, informant=fakes.Informant())

    config = Trader.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=2,
        end=6,
        quote=Decimal('1.0'),
        strategy='fixed',
        strategy_kwargs={'advices': ['none'] * 100, 'maturity': 2},
        adjust_start=True,
    )
    state = Trader.State()

    trader_run_task = asyncio.create_task(trader.run(config, state))

    future_candle_queue = chandler.future_candle_queues[('dummy', 'eth-btc', 1)]
    await future_candle_queue.join()
    await cancel(trader_run_task)
    await storage.set('shard', 'key', state)
    future_candle_queue.put_nowait(Candle(time=5))
    state = await storage.get('shard', 'key', Trader.State)

    await trader.run(config, state)

    assert state.strategy
    candle_times = [c.time for c in state.strategy.updates]  # type: ignore
    assert len(candle_times) == 6
    assert candle_times[0] == 0
    assert candle_times[1] == 1
    assert candle_times[2] == 2
    assert candle_times[3] == 3
    assert candle_times[4] == 4
    assert candle_times[5] == 5


async def test_multitrader() -> None:
    symbols = ['eth-btc', 'ltc-btc', 'xmr-btc']
    chandler = fakes.Chandler(
        future_candles={('dummy', s, 1): [Candle(time=0, close=Decimal('1.0'))] for s in symbols},
    )
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('3.0'), quote_volume=Decimal('3.0')),
        Ticker(symbol='ltc-btc', volume=Decimal('2.0'), quote_volume=Decimal('2.0')),
        Ticker(symbol='xmr-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = MultiTrader(chandler=chandler, informant=informant)
    config = MultiTrader.Config(
        exchange='dummy',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('2.0'),
        strategy='fixed',
        strategy_kwargs={'advices': ['long', 'liquidate', 'short', 'short']},
        long=True,
        short=True,
        track_count=3,
        position_count=2,
    )

    trader_task = asyncio.create_task(trader.run(config))

    for i in range(1, 4):
        await asyncio.gather(
            *(chandler.future_candle_queues[('dummy', s, 1)].join() for s in symbols)
        )
        # Sleep to give control back to position manager.
        await asyncio.sleep(0)
        for s in symbols:
            chandler.future_candle_queues[('dummy', s, 1)].put_nowait(
                Candle(time=i, close=Decimal('1.0'))
            )

    summary = await trader_task

    #     L - S S
    # ETH L - S S
    # LTC L - S S
    # XMR - - - -
    long_positions = list(summary.get_long_positions())
    short_positions = list(summary.get_short_positions())
    assert len(long_positions) == 2
    assert len(short_positions) == 2
    assert long_positions[0].open_time == 0
    assert long_positions[0].close_time == 1
    assert long_positions[0].symbol == 'eth-btc'
    assert long_positions[1].open_time == 0
    assert long_positions[1].close_time == 1
    assert long_positions[1].symbol == 'ltc-btc'
    assert short_positions[0].open_time == 2
    assert short_positions[0].close_time == 3
    assert short_positions[0].symbol == 'eth-btc'
    assert short_positions[1].open_time == 2
    assert short_positions[1].close_time == 3
    assert short_positions[1].symbol == 'ltc-btc'


def new_closed_long_position(profit: Decimal) -> Position.Long:
    size = abs(profit)
    price = Decimal('1.0') if profit >= 0 else Decimal('-1.0')
    open_pos = Position.OpenLong(
        symbol='eth-btc',
        time=0,
        fills=[
            Fill(price=Decimal('0.0'), size=size, quote=Decimal('0.0'), fee_asset='eth'),
        ],
    )
    return open_pos.close(
        time=1,
        fills=[
            Fill(price=price, size=size, quote=Decimal(price * size), fee_asset='btc'),
        ]
    )
