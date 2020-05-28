import asyncio
from decimal import Decimal
from typing import cast

from juno import BorrowInfo, Candle, Filters, MissedCandlePolicy, Ticker, strategies, traders
from juno.asyncio import cancel
from juno.config import get_module_type_constructor
from juno.trading import CloseReason

from . import fakes


async def test_basic_upside_trailing_stop() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('10.0')),  # Open long.
            Candle(time=1, close=Decimal('20.0')),
            Candle(time=2, close=Decimal('18.0')),  # Trigger trailing stop (10%).
            Candle(time=3, close=Decimal('10.0')),  # Close long (do not act).
        ]
    })
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('10.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['long', 'long', 'long', 'liquidate'],
                'ignore_mid_trend': False,
            },
        ),
        trailing_stop=Decimal('0.1'),
        long=True,
        short=False,
    )
    summary = await trader.run(config)

    assert summary.profit == 8

    long_positions = list(summary.get_long_positions())
    assert len(long_positions) == 1
    assert long_positions[0].close_reason is CloseReason.TRAILING_STOP


async def test_basic_downside_trailing_stop() -> None:
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
    trader = traders.Basic(chandler=chandler, informant=informant)

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('10.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['short', 'short', 'short', 'liquidate'],
                'ignore_mid_trend': False,
            },
        ),
        trailing_stop=Decimal('0.1'),
        long=False,
        short=True,
    )
    summary = await trader.run(config)

    assert summary.profit == 4

    short_positions = list(summary.get_short_positions())
    assert len(short_positions) == 1
    assert short_positions[0].close_reason is CloseReason.TRAILING_STOP


async def test_basic_restart_on_missed_candle() -> None:
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
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('10.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none'] * 3,
            },
        ),
        missed_candle_policy=MissedCandlePolicy.RESTART,
    )
    initial_strategy = cast(strategies.Fixed, config.strategy.construct())
    state = traders.Basic.State(strategy=initial_strategy)
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


async def test_basic_assume_same_as_last_on_missed_candle() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0),
            Candle(time=1),
            # 2 candles skipped.
            Candle(time=4),  # Generate new candles with previous data.
        ]
    })
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=5,
        quote=Decimal('10.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none'] * 5,
            },
        ),
        missed_candle_policy=MissedCandlePolicy.LAST,
    )
    state = traders.Basic.State()
    await trader.run(config, state)

    assert state.strategy

    candle_times = [c.time for c in state.strategy.updates]  # type: ignore
    assert len(candle_times) == 5
    assert candle_times[0] == 0
    assert candle_times[1] == 1
    assert candle_times[2] == 2
    assert candle_times[3] == 3
    assert candle_times[4] == 4


async def test_basic_adjust_start_ignore_mid_trend() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
            Candle(time=2, close=Decimal('1.0')),
            Candle(time=3, close=Decimal('1.0')),
        ]
    })
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=2,
        end=4,
        quote=Decimal('1.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none', 'long', 'long', 'none'],
                'maturity': 1,
                'ignore_mid_trend': True,
                'persistence': 1,
            },
        ),
        adjust_start=True,
    )

    summary = await trader.run(config)

    assert summary.num_positions == 0


async def test_basic_adjust_start_persistence() -> None:
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1):
        [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
            Candle(time=2, close=Decimal('1.0')),
            Candle(time=3, close=Decimal('1.0')),
        ]
    })
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=3,
        end=4,
        quote=Decimal('1.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none', 'long', 'long', 'long'],
                'maturity': 1,
                'ignore_mid_trend': False,
                'persistence': 2,
            },
        ),
        adjust_start=True,
    )

    summary = await trader.run(config)

    assert summary.num_positions == 1
    assert summary.num_long_positions == 1
    assert list(summary.get_long_positions())[0].close_reason is CloseReason.CANCELLED


async def test_basic_persist_and_resume(storage: fakes.Storage) -> None:
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
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=2,
        end=6,
        quote=Decimal('1.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none'] * 100,
                'maturity': 2,
            },
        ),
        adjust_start=True,
    )
    state = traders.Basic.State()

    trader_run_task = asyncio.create_task(trader.run(config, state))

    future_candle_queue = chandler.future_candle_queues[('dummy', 'eth-btc', 1)]
    await future_candle_queue.join()
    await cancel(trader_run_task)
    await storage.set('shard', 'key', state)
    future_candle_queue.put_nowait(Candle(time=5))
    state = await storage.get('shard', 'key', traders.Basic.State)

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


async def test_basic_summary_end_on_cancel() -> None:
    chandler = fakes.Chandler(future_candles={('dummy', 'eth-btc', 1): [Candle(time=0)]})
    time = fakes.Time(0)
    trader = traders.Basic(
        chandler=chandler, informant=fakes.Informant(), get_time_ms=time.get_time
    )

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=10,
        quote=Decimal('1.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none'] * 100,
            },
        ),
    )
    state = traders.Basic.State()

    trader_run_task = asyncio.create_task(trader.run(config, state))

    future_candle_queue = chandler.future_candle_queues[('dummy', 'eth-btc', 1)]
    await future_candle_queue.join()

    time.time = 5
    await cancel(trader_run_task)

    assert state.summary
    assert state.summary.start == 0
    assert state.summary.end == 5


async def test_basic_summary_end_on_historical_cancel() -> None:
    # Even though we simulate historical trading, we can use `future_candles` to perform
    # synchronization for testing.
    chandler = fakes.Chandler(future_candles={('dummy', 'eth-btc', 1): [Candle(time=0)]})
    time = fakes.Time(100)
    trader = traders.Basic(
        chandler=chandler, informant=fakes.Informant(), get_time_ms=time.get_time
    )

    config = traders.Basic.Config(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=2,
        quote=Decimal('1.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['none'] * 100,
            },
        ),
    )
    state = traders.Basic.State()

    trader_run_task = asyncio.create_task(trader.run(config, state))

    future_candle_queue = chandler.future_candle_queues[('dummy', 'eth-btc', 1)]
    await future_candle_queue.join()

    await cancel(trader_run_task)

    assert state.summary
    assert state.summary.start == 0
    assert state.summary.end == 1


async def test_multi() -> None:
    symbols = ['eth-btc', 'ltc-btc', 'xmr-btc']
    chandler = fakes.Chandler(
        future_candles={('dummy', s, 1): [Candle(time=0, close=Decimal('1.0'))] for s in symbols},
    )
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('3.0'), quote_volume=Decimal('3.0')),
        Ticker(symbol='ltc-btc', volume=Decimal('2.0'), quote_volume=Decimal('2.0')),
        Ticker(symbol='xmr-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.Multi.Config(
        exchange='dummy',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('2.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['long', 'liquidate', 'short', 'short'],
            },
        ),
        symbol_strategies={
            'xmr-btc': get_module_type_constructor(
                strategies,
                {
                    'type': 'fixed',
                    'advices': ['liquidate', 'long', 'long', 'long'],
                },
            ),
        },
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
    # LTC L - - -

    #     - L L L
    # XMR - L L L
    long_positions = list(summary.get_long_positions())
    short_positions = list(summary.get_short_positions())
    assert len(long_positions) == 3
    assert len(short_positions) == 1
    pos = long_positions[0]
    assert pos.open_time == 1
    assert pos.close_time == 2
    assert pos.symbol == 'eth-btc'
    assert pos.close_reason is CloseReason.STRATEGY
    pos = long_positions[1]
    assert pos.open_time == 1
    assert pos.close_time == 2
    assert pos.symbol == 'ltc-btc'
    assert pos.close_reason is CloseReason.STRATEGY
    pos = long_positions[2]
    assert pos.open_time == 2
    assert pos.close_time == 4
    assert pos.symbol == 'xmr-btc'
    assert pos.close_reason is CloseReason.CANCELLED
    pos = short_positions[0]
    assert pos.open_time == 3
    assert pos.close_time == 4
    assert pos.symbol == 'eth-btc'
    assert pos.close_reason is CloseReason.CANCELLED


async def test_multi_persist_and_resume(storage: fakes.Storage) -> None:
    symbols = ['eth-btc', 'ltc-btc']
    chandler = fakes.Chandler()
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('2.0'), quote_volume=Decimal('2.0')),
        Ticker(symbol='ltc-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.Multi.Config(
        exchange='dummy',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('2.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['long', 'liquidate', 'short', 'short'],
            },
        ),
        symbol_strategies={
            'ltc-btc': get_module_type_constructor(
                strategies,
                {
                    'type': 'fixed',
                    'advices': ['liquidate', 'long', 'liquidate', 'short'],
                },
            ),
        },
        long=True,
        short=True,
        track_count=2,
        position_count=1,
    )

    trader_state = traders.Multi.State()
    for i in range(0, 4):
        trader_task = asyncio.create_task(trader.run(config, trader_state))

        for s in symbols:
            chandler.future_candle_queues[('dummy', s, 1)].put_nowait(
                Candle(time=i, close=Decimal('1.0'))
            )
        await asyncio.gather(
            *(chandler.future_candle_queues[('dummy', s, 1)].join() for s in symbols)
        )
        # Sleep to give control back to position manager.
        await asyncio.sleep(0)

        if i < 3:
            await cancel(trader_task)
            await storage.set('shard', 'key', trader_state)
            trader_state = await storage.get('shard', 'key', traders.Multi.State)

    summary = await trader_task

    #     L - S S
    # ETH L - S -  NB! Losing the short because positions get liquidated on cancel.

    #     - L - S
    # LTC - L - S
    long_positions = list(summary.get_long_positions())
    short_positions = list(summary.get_short_positions())
    assert len(long_positions) == 2
    assert len(short_positions) == 2
    pos = long_positions[0]
    assert pos.open_time == 1
    assert pos.close_time == 1
    assert pos.symbol == 'eth-btc'
    assert pos.close_reason is CloseReason.CANCELLED
    pos = long_positions[1]
    assert pos.open_time == 2
    assert pos.close_time == 2
    assert pos.symbol == 'ltc-btc'
    assert pos.close_reason is CloseReason.CANCELLED
    pos = short_positions[0]
    assert pos.open_time == 3
    assert pos.close_time == 3
    assert pos.symbol == 'eth-btc'
    assert pos.close_reason is CloseReason.CANCELLED
    pos = short_positions[1]
    assert pos.open_time == 4
    assert pos.close_time == 4
    assert pos.symbol == 'ltc-btc'
    assert pos.close_reason is CloseReason.CANCELLED


async def test_multi_historical() -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', 'eth-btc', 1): [Candle(time=i, close=Decimal('1.0')) for i in range(10)],
            # Missing first half of candles. Should tick empty advice for missing.
            ('dummy', 'ltc-btc', 1): [Candle(time=i, close=Decimal('1.0')) for i in range(5, 10)],
        },
    )
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('2.0'), quote_volume=Decimal('2.0')),
        Ticker(symbol='ltc-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = trader.Config(
        exchange='dummy',
        interval=1,
        start=0,
        end=10,
        quote=Decimal('2.0'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['long'] * 10,
            },
        ),
        long=True,
        short=True,
        track_count=2,
        position_count=2,
    )

    summary = await trader.run(config)

    long_positions = list(summary.get_long_positions())
    assert len(long_positions) == 2
    pos = long_positions[0]
    assert pos.symbol == 'eth-btc'
    assert pos.open_time == 1
    assert pos.close_time == 10
    assert pos.close_reason is CloseReason.CANCELLED
    pos = long_positions[1]
    assert pos.symbol == 'ltc-btc'
    assert pos.open_time == 6
    assert pos.close_time == 10
    assert pos.close_reason is CloseReason.CANCELLED


async def test_multi_trailing_stop() -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', 'eth-btc', 1): [
                Candle(time=0, close=Decimal('3.0')),
                Candle(time=1, close=Decimal('1.0')),  # Triggers trailing stop.
                Candle(time=2, close=Decimal('1.0')),
                Candle(time=3, close=Decimal('1.0')),
                Candle(time=4, close=Decimal('1.0')),
                Candle(time=5, close=Decimal('1.0')),
            ],
        },
    )
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = trader.Config(
        exchange='dummy',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('3.0'),
        trailing_stop=Decimal('0.5'),
        strategy=get_module_type_constructor(
            strategies,
            {
                'type': 'fixed',
                'advices': ['long', 'long', 'long', 'liquidate', 'long', 'long'],
            },
        ),
        long=True,
        short=True,
        track_count=1,
        position_count=1,
    )

    summary = await trader.run(config)

    long_positions = list(summary.get_long_positions())
    assert len(long_positions) == 2
    pos = long_positions[0]
    assert pos.open_time == 1
    assert pos.close_time == 2
    assert pos.close_reason is CloseReason.TRAILING_STOP
    pos = long_positions[1]
    assert pos.open_time == 5
    assert pos.close_time == 6
    assert pos.close_reason is CloseReason.CANCELLED
