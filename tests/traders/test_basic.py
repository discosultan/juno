import asyncio
from decimal import Decimal

import pytest

from juno import Advice, BorrowInfo, Candle, Filters, stop_loss, take_profit, traders
from juno.asyncio import cancel
from juno.inspect import GenericConstructor
from juno.strategies import Fixed, MidTrendPolicy
from juno.trading import CloseReason, Position
from tests import fakes


async def test_upside_stop_loss() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("10.0")),  # Open long.
                Candle(time=1, close=Decimal("20.0")),
                Candle(time=2, close=Decimal("18.0")),
                Candle(time=3, close=Decimal("8.0")),  # Trigger trailing stop loss (10%).
                Candle(time=4, close=Decimal("10.0")),  # Close long (do not act).
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=5,
        quote=Decimal("10.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG, Advice.LONG, Advice.LONG, Advice.LIQUIDATE],
            mid_trend_policy=MidTrendPolicy.CURRENT,
        ),
        stop_loss=GenericConstructor.from_type(stop_loss.Basic, Decimal("0.1")),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    positions = summary.positions
    assert len(positions) == 1
    position = positions[0]
    assert isinstance(position, Position.Long)
    assert position.profit == -2
    assert position.close_reason is CloseReason.STOP_LOSS


async def test_upside_trailing_stop_loss() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("10.0")),  # Open long.
                Candle(time=1, close=Decimal("20.0")),
                Candle(time=2, close=Decimal("18.0")),  # Trigger trailing stop loss (10%).
                Candle(time=3, close=Decimal("10.0")),  # Close long (do not act).
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=4,
        quote=Decimal("10.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG, Advice.LONG, Advice.LIQUIDATE],
            mid_trend_policy=MidTrendPolicy.CURRENT,
        ),
        stop_loss=GenericConstructor.from_type(stop_loss.Trailing, Decimal("0.1")),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    positions = summary.positions
    assert len(positions) == 1
    position = positions[0]
    assert isinstance(position, Position.Long)
    assert position.profit == 8
    assert position.close_reason is CloseReason.STOP_LOSS


async def test_downside_trailing_stop_loss() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("10.0")),  # Open short.
                Candle(time=1, close=Decimal("5.0")),
                Candle(time=2, close=Decimal("6.0")),  # Trigger trailing stop loss (10%).
                Candle(time=3, close=Decimal("10.0")),  # Close short (do not act).
            ]
        }
    )
    informant = fakes.Informant(
        filters=Filters(isolated_margin=True),
        borrow_info=BorrowInfo(limit=Decimal("1.0")),
        margin_multiplier=2,
    )
    trader = traders.Basic(chandler=chandler, informant=informant)
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=4,
        quote=Decimal("10.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.SHORT, Advice.SHORT, Advice.SHORT, Advice.LIQUIDATE],
            mid_trend_policy=MidTrendPolicy.CURRENT,
        ),
        stop_loss=GenericConstructor.from_type(stop_loss.Trailing, Decimal("0.1")),
        long=False,
        short=True,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    assert summary.profit == 4

    short_positions = [p for p in summary.positions if isinstance(p, Position.Short)]
    assert len(short_positions) == 1
    assert short_positions[0].close_reason is CloseReason.STOP_LOSS


async def test_upside_take_profit() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("10.0")),  # Open long.
                Candle(time=1, close=Decimal("12.0")),
                Candle(time=2, close=Decimal("20.0")),  # Trigger take profit (50%).
                Candle(time=3, close=Decimal("10.0")),  # Close long (do not act).
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=4,
        quote=Decimal("10.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG, Advice.LONG, Advice.LIQUIDATE],
            mid_trend_policy=MidTrendPolicy.CURRENT,
        ),
        take_profit=GenericConstructor.from_type(take_profit.Basic, Decimal("0.5")),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    assert summary.profit == 10

    long_positions = [p for p in summary.positions if isinstance(p, Position.Long)]
    assert len(long_positions) == 1
    assert long_positions[0].close_reason is CloseReason.TAKE_PROFIT


async def test_downside_take_profit() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("10.0")),  # Open short.
                Candle(time=1, close=Decimal("8.0")),
                Candle(time=2, close=Decimal("4.0")),  # Trigger take profit (50%).
                Candle(time=3, close=Decimal("10.0")),  # Close short (do not act).
            ]
        }
    )
    informant = fakes.Informant(
        filters=Filters(isolated_margin=True),
        borrow_info=BorrowInfo(limit=Decimal("1.0")),
        margin_multiplier=2,
    )
    trader = traders.Basic(chandler=chandler, informant=informant)
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=4,
        quote=Decimal("10.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.SHORT, Advice.SHORT, Advice.SHORT, Advice.LIQUIDATE],
            mid_trend_policy=MidTrendPolicy.CURRENT,
        ),
        take_profit=GenericConstructor.from_type(take_profit.Basic, Decimal("0.5")),
        long=False,
        short=True,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    assert summary.profit == 6

    short_positions = [p for p in summary.positions if isinstance(p, Position.Short)]
    assert len(short_positions) == 1
    assert short_positions[0].close_reason is CloseReason.TAKE_PROFIT


async def test_adjusted_start_ignore_mid_trend() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("1.0")),
                Candle(time=1, close=Decimal("1.0")),
                Candle(time=2, close=Decimal("1.0")),
                Candle(time=3, close=Decimal("1.0")),
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=2,
        end=4,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.NONE, Advice.LONG, Advice.LONG, Advice.NONE],
            maturity=2,
            mid_trend_policy=MidTrendPolicy.IGNORE,
            persistence=1,
        ),
        adjusted_start="strategy",
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    assert len(summary.positions) == 0


async def test_adjusted_start_persistence() -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("1.0")),
                Candle(time=1, close=Decimal("1.0")),
                Candle(time=2, close=Decimal("1.0")),
                Candle(time=3, close=Decimal("1.0")),
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=3,
        end=4,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.NONE, Advice.LONG, Advice.LONG, Advice.LONG],
            maturity=2,
            mid_trend_policy=MidTrendPolicy.CURRENT,
            persistence=2,
        ),
        adjusted_start="strategy",
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    long_positions = [p for p in summary.positions if isinstance(p, Position.Long)]
    assert len(long_positions) == 1
    assert long_positions[0].close_reason is CloseReason.CANCELLED


async def test_persist_and_resume(storage: fakes.Storage) -> None:
    chandler = fakes.Chandler(
        candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0),
                Candle(time=1),
                Candle(time=2),
                Candle(time=3),
            ]
        },
        future_candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=4),
            ]
        },
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=2,
        end=6,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            maturity=3,
        ),
        adjusted_start="strategy",
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    trader_run_task = asyncio.create_task(trader.run(state))

    future_candle_queue = chandler.future_candle_queues[("dummy", "eth-btc", 1)]
    await future_candle_queue.join()
    await cancel(trader_run_task)
    await storage.set("shard", "key", state)
    future_candle_queue.put_nowait(Candle(time=5))
    state = await storage.get("shard", "key", traders.BasicState)

    await trader.run(state)

    candle_times = [c.time for c in state.strategy.updates]  # type: ignore
    assert len(candle_times) == 6
    for i in range(6):
        assert candle_times[i] == i


async def test_summary_end_on_cancel() -> None:
    chandler = fakes.Chandler(future_candles={("dummy", "eth-btc", 1): [Candle(time=0)]})
    time = fakes.Time(0)
    trader = traders.Basic(
        chandler=chandler, informant=fakes.Informant(), get_time_ms=time.get_time
    )

    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=10,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(Fixed),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    trader_run_task = asyncio.create_task(trader.run(state))

    future_candle_queue = chandler.future_candle_queues[("dummy", "eth-btc", 1)]
    await future_candle_queue.join()

    time.time = 5
    await cancel(trader_run_task)

    summary = trader.build_summary(state)

    assert summary
    assert summary.start == 0
    assert summary.end == 5


async def test_summary_end_on_historical_cancel() -> None:
    # Even though we simulate historical trading, we can use `future_candles` to perform
    # synchronization for testing.
    chandler = fakes.Chandler(future_candles={("dummy", "eth-btc", 1): [Candle(time=0)]})
    time = fakes.Time(100)
    trader = traders.Basic(
        chandler=chandler, informant=fakes.Informant(), get_time_ms=time.get_time
    )

    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=2,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(Fixed),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    trader_run_task = asyncio.create_task(trader.run(state))

    future_candle_queue = chandler.future_candle_queues[("dummy", "eth-btc", 1)]
    await future_candle_queue.join()

    await cancel(trader_run_task)

    summary = trader.build_summary(state)

    assert summary
    assert summary.start == 0
    assert summary.end == 1


@pytest.mark.parametrize(
    "close_on_exit,expected_close_time,expected_close_reason,expected_profit",
    [
        (False, 3, CloseReason.STRATEGY, Decimal("2.0")),
        (True, 2, CloseReason.CANCELLED, Decimal("1.0")),
    ],
)
async def test_close_on_exit(
    storage: fakes.Storage,
    close_on_exit: bool,
    expected_close_time: int,
    expected_close_reason: CloseReason,
    expected_profit: Decimal,
) -> None:
    chandler = fakes.Chandler(
        future_candles={
            ("dummy", "eth-btc", 1): [
                Candle(time=0, close=Decimal("1.0")),  # Long.
                Candle(time=1, close=Decimal("2.0")),
            ]
        }
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=4,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG, Advice.SHORT, Advice.SHORT],
        ),
        close_on_exit=close_on_exit,
        long=True,
        short=False,
    )
    state = await trader.initialize(config)

    trader_run_task = asyncio.create_task(trader.run(state))

    future_candle_queue = chandler.future_candle_queues[("dummy", "eth-btc", 1)]
    await future_candle_queue.join()
    await cancel(trader_run_task)
    # Liquidate if close on exit.
    await storage.set("shard", "key", state)
    future_candle_queue.put_nowait(Candle(time=2, close=Decimal("3.0")))
    # Liquidate if not close on exit.
    future_candle_queue.put_nowait(Candle(time=3, close=Decimal("4.0")))
    state = await storage.get("shard", "key", traders.BasicState)

    summary = await trader.run(state)
    assert summary.start == 0
    assert summary.end == 4

    positions = summary.positions
    assert len(positions) == 1

    position = positions[0]
    assert isinstance(position, Position.Long)
    assert position.open_time == 1
    assert position.close_time == expected_close_time
    assert position.close_reason is expected_close_reason
    assert position.profit == expected_profit


async def test_open_new_positions() -> None:
    chandler = fakes.Chandler(
        candles={("dummy", "eth-btc", 1): [Candle(time=0, close=Decimal("1.0"))]}
    )
    trader = traders.Basic(chandler=chandler, informant=fakes.Informant())
    config = traders.BasicConfig(
        exchange="dummy",
        symbol="eth-btc",
        interval=1,
        start=0,
        end=1,
        quote=Decimal("1.0"),
        strategy=GenericConstructor.from_type(
            Fixed,
            advices=[Advice.LONG],
        ),
        long=True,
        short=False,
    )
    state = await trader.initialize(config)
    state.open_new_positions = False

    summary = await trader.run(state)

    assert len(summary.positions) == 0
