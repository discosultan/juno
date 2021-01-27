import asyncio
from decimal import Decimal

import pytest

from juno import (
    Advice, Balance, Candle, Fees, Fill, Filters, OrderResult, OrderStatus, Ticker, stop_loss,
    take_profit, traders
)
from juno.asyncio import cancel
from juno.strategies import Fixed
from juno.trading import CloseReason, Position, TradingMode
from juno.typing import TypeConstructor
from tests import fakes


async def test_simple() -> None:
    symbols = ['eth-btc', 'ltc-btc', 'xmr-btc']
    chandler = fakes.Chandler(
        future_candles={('dummy', s, 1): [Candle(time=0, close=Decimal('1.0'))] for s in symbols},
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('3.0'),
            quote_volume=Decimal('3.0'),
            price=Decimal('1.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('1.0'),
        ),
        'xmr-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('1'),  # Deliberately 1 and not 1.0. Shouldn't screw up splitting.
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LIQUIDATE, Advice.SHORT, Advice.SHORT],
        ),
        symbol_strategies={
            'xmr-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LIQUIDATE, Advice.LONG, Advice.LONG, Advice.LONG],
            ),
        },
        long=True,
        short=True,
        track_count=3,
        position_count=2,
    )
    state = await trader.initialize(config)

    trader_task = asyncio.create_task(trader.run(state))

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
    long_positions = summary.list_positions(type_=Position.Long)
    short_positions = summary.list_positions(type_=Position.Short)
    assert len(long_positions) == 3
    assert len(short_positions) == 1
    lpos = long_positions[0]
    assert lpos.open_time == 1
    assert lpos.close_time == 2
    assert lpos.symbol == 'eth-btc'
    assert lpos.close_reason is CloseReason.STRATEGY
    lpos = long_positions[1]
    assert lpos.open_time == 1
    assert lpos.close_time == 2
    assert lpos.symbol == 'ltc-btc'
    assert lpos.close_reason is CloseReason.STRATEGY
    lpos = long_positions[2]
    assert lpos.open_time == 2
    assert lpos.close_time == 4
    assert lpos.symbol == 'xmr-btc'
    assert lpos.close_reason is CloseReason.CANCELLED
    spos = short_positions[0]
    assert spos.open_time == 3
    assert spos.close_time == 4
    assert spos.symbol == 'eth-btc'
    assert spos.close_reason is CloseReason.CANCELLED


async def test_persist_and_resume(storage: fakes.Storage) -> None:
    symbols = ['eth-btc', 'ltc-btc']
    chandler = fakes.Chandler()
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('1.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=4,
        quote=Decimal('2.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LIQUIDATE, Advice.SHORT, Advice.SHORT],
        ),
        symbol_strategies={
            'ltc-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LIQUIDATE, Advice.LONG, Advice.LIQUIDATE, Advice.SHORT],
            ),
        },
        long=True,
        short=True,
        track_count=2,
        position_count=1,
    )

    trader_state = await trader.initialize(config)
    for i in range(0, 4):
        trader_task = asyncio.create_task(trader.run(trader_state))

        for s in symbols:
            chandler.future_candle_queues[('dummy', s, 1)].put_nowait(
                Candle(time=i, close=Decimal('1.0'))
            )
        await asyncio.gather(
            *(chandler.future_candle_queues[('dummy', s, 1)].join() for s in symbols)
        )
        # Sleep to give control back to position manager.
        await asyncio.sleep(0)

        if i < 3:  # If not last iteration, cancel, store and retrieve from storage.
            await cancel(trader_task)
            await storage.set('shard', 'key', trader_state)
            trader_state = await storage.get('shard', 'key', traders.MultiState)

            # Change tickers for informant. This shouldn't crash the trader.
            informant.tickers['xmr-btc'] = Ticker(
                volume=Decimal('3.0'),
                quote_volume=Decimal('3.0'),
                price=Decimal('1.0'),
            )

    summary = await trader_task

    #     L - S S
    # ETH L - S -  NB! Losing the short because positions get liquidated on cancel.

    #     - L - S
    # LTC - L - S
    long_positions = summary.list_positions(type_=Position.Long)
    short_positions = summary.list_positions(type_=Position.Short)
    assert len(long_positions) == 2
    assert len(short_positions) == 2
    lpos = long_positions[0]
    assert lpos.open_time == 1
    assert lpos.close_time == 1
    assert lpos.symbol == 'eth-btc'
    assert lpos.close_reason is CloseReason.CANCELLED
    lpos = long_positions[1]
    assert lpos.open_time == 2
    assert lpos.close_time == 2
    assert lpos.symbol == 'ltc-btc'
    assert lpos.close_reason is CloseReason.CANCELLED
    spos = short_positions[0]
    assert spos.open_time == 3
    assert spos.close_time == 3
    assert spos.symbol == 'eth-btc'
    assert spos.close_reason is CloseReason.CANCELLED
    spos = short_positions[1]
    assert spos.open_time == 4
    assert spos.close_time == 4
    assert spos.symbol == 'ltc-btc'
    assert spos.close_reason is CloseReason.CANCELLED


async def test_historical() -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', 'eth-btc', 1): [Candle(time=i, close=Decimal('1.0')) for i in range(10)],
            # Missing first half of candles. Should tick empty advice for missing.
            ('dummy', 'ltc-btc', 1): [Candle(time=i, close=Decimal('1.0')) for i in range(5, 10)],
        },
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('1.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=10,
        quote=Decimal('2.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG] * 10,
        ),
        long=True,
        short=True,
        track_count=2,
        position_count=2,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    long_positions = summary.list_positions(type_=Position.Long)
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


async def test_trailing_stop_loss() -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', 'eth-btc', 1): [
                Candle(time=0, close=Decimal('3.0')),
                Candle(time=1, close=Decimal('1.0')),  # Triggers trailing stop loss.
                Candle(time=2, close=Decimal('1.0')),
                Candle(time=3, close=Decimal('1.0')),
                Candle(time=4, close=Decimal('1.0')),
                Candle(time=5, close=Decimal('1.0')),
            ],
        },
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=6,
        quote=Decimal('3.0'),
        stop_loss=TypeConstructor.from_type(stop_loss.Basic, Decimal('0.5')),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[
                Advice.LONG,
                Advice.LONG,
                Advice.LONG,
                Advice.LIQUIDATE,
                Advice.LONG,
                Advice.LONG,
            ],
        ),
        long=True,
        short=True,
        track_count=1,
        position_count=1,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    long_positions = summary.list_positions(type_=Position.Long)
    assert len(long_positions) == 2
    pos = long_positions[0]
    assert pos.open_time == 1
    assert pos.close_time == 2
    assert pos.close_reason is CloseReason.STOP_LOSS
    pos = long_positions[1]
    assert pos.open_time == 5
    assert pos.close_time == 6
    assert pos.close_reason is CloseReason.CANCELLED


@pytest.mark.parametrize(
    'close_on_exit,expected_close_time,expected_close_reason,expected_profit',
    [
        (False, 3, CloseReason.STRATEGY, Decimal('2.0')),
        (True, 2, CloseReason.CANCELLED, Decimal('1.0')),
    ],
)
async def test_close_on_exit(
    storage: fakes.Storage,
    close_on_exit: bool,
    expected_close_time: int,
    expected_close_reason: CloseReason,
    expected_profit: Decimal,
) -> None:
    symbols = ['eth-btc', 'ltc-btc']
    chandler = fakes.Chandler(
        future_candles={
            ('dummy', 'eth-btc', 1): [
                Candle(time=0, close=Decimal('10.0')),
                Candle(time=1, close=Decimal('20.0')),
            ],
            ('dummy', 'ltc-btc', 1): [
                Candle(time=0, close=Decimal('1.0')),
                Candle(time=1, close=Decimal('2.0')),
            ],
        },
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('1.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=3,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG, Advice.LIQUIDATE],
        ),
        long=True,
        short=True,
        track_count=2,
        position_count=1,
        close_on_exit=close_on_exit,
    )
    state = await trader.initialize(config)

    trader_task = asyncio.create_task(trader.run(state))

    await asyncio.gather(
        *(chandler.future_candle_queues[('dummy', s, 1)].join() for s in symbols)
    )
    # Sleep to give control back to position manager.
    await asyncio.sleep(0)

    await cancel(trader_task)
    await storage.set('shard', 'key', state)
    state = await storage.get('shard', 'key', traders.MultiState)
    chandler.future_candle_queues[('dummy', 'eth-btc', 1)].put_nowait(
        Candle(time=2, close=Decimal('30.0'))
    )
    chandler.future_candle_queues[('dummy', 'ltc-btc', 1)].put_nowait(
        Candle(time=2, close=Decimal('3.0'))
    )
    summary = await trader.run(state)

    # close_on_exit = True
    #     L L -
    # ETH L L -
    # LTC - - -

    # close_on_exit = False
    #     L L -
    # ETH L L L
    # LTC - - -

    positions = summary.list_positions()
    assert len(positions) == 1

    position = positions[0]
    assert isinstance(position, Position.Long)
    assert position.symbol == 'eth-btc'
    assert position.open_time == 1
    assert position.close_time == expected_close_time
    assert position.close_reason is expected_close_reason
    assert position.profit == expected_profit


async def test_quote_not_requested_when_resumed_in_live_mode(mocker) -> None:
    user = mocker.patch('juno.components.user.User', autospec=True)
    user.get_balance.return_value = Balance(Decimal('1.0'))
    broker = mocker.patch('juno.brokers.market.Market', autospec=True)
    broker.buy.return_value = OrderResult(
        time=0,
        status=OrderStatus.FILLED,
        fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
    )

    chandler = fakes.Chandler(
        future_candles={('dummy', 'eth-btc', 1): [Candle(time=0, close=Decimal('1.0'))]},
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant, user=user, broker=broker)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=2,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.LONG],
        ),
        long=True,
        track_count=1,
        position_count=1,
        close_on_exit=False,
        mode=TradingMode.LIVE,
    )
    state = await trader.initialize(config)

    trader_task = asyncio.create_task(trader.run(state))
    await chandler.future_candle_queues[('dummy', 'eth-btc', 1)].join()
    # Sleep to give control back to position manager.
    await asyncio.sleep(0)
    await cancel(trader_task)

    chandler.future_candle_queues[('dummy', 'eth-btc', 1)].put_nowait(
        Candle(time=1, close=Decimal('2.0'))
    )

    user.get_balance.return_value = Balance(Decimal('0.0'))
    await trader.run(state)


async def test_open_new_positions() -> None:
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1): [Candle(time=0, close=Decimal('1.0'))]
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=1,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG],
        ),
        long=True,
        track_count=1,
        position_count=1,
    )
    state = await trader.initialize(config)
    state.open_new_positions = False

    summary = await trader.run(state)

    assert len(summary.list_positions()) == 0


async def test_take_profit() -> None:
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1): [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('2.0')),
        ],
    })
    trader = traders.Multi(chandler=chandler, informant=informant)

    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=2,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG, Advice.NONE],
        ),
        long=True,
        track_count=1,
        position_count=1,
        take_profit=TypeConstructor.from_type(take_profit.Basic, Decimal('0.5')),
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    positions = summary.list_positions()
    assert len(positions) == 1
    assert positions[0].close_reason is CloseReason.TAKE_PROFIT


async def test_repick_symbols() -> None:
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('2.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    chandler = fakes.Chandler(future_candles={
        ('dummy', 'eth-btc', 1): [Candle(time=0, close=Decimal('2.0'))],
        ('dummy', 'ltc-btc', 1): [Candle(time=0, close=Decimal('1.0'))],
    })
    trader = traders.Multi(chandler=chandler, informant=informant)

    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=2,
        quote=Decimal('2.0'),
        strategy=TypeConstructor.from_type(Fixed),
        symbol_strategies={
            'eth-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LONG, Advice.NONE],
            ),
            'ltc-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.NONE, Advice.NONE],
            ),
            'xmr-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LONG],
            ),
        },
        long=True,
        track_count=2,
        position_count=2,
        close_on_exit=True,
        adjust_start=False,
    )
    state = await trader.initialize(config)
    informant.tickers = {
        'xmr-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('2.0'),
        ),
        'xrp-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    }

    task = asyncio.create_task(trader.run(state))

    await asyncio.gather(
        chandler.future_candle_queues[('dummy', 'eth-btc', 1)].join(),
        chandler.future_candle_queues[('dummy', 'ltc-btc', 1)].join(),
    )
    chandler.future_candle_queues[('dummy', 'eth-btc', 1)].put_nowait(
        Candle(time=1, close=Decimal('1.0'))
    )
    chandler.future_candle_queues[('dummy', 'xmr-btc', 1)].put_nowait(
        Candle(time=1, close=Decimal('1.0'))
    )

    summary = await asyncio.wait_for(task, timeout=1.0)

    positions = summary.list_positions()
    assert len(positions) == 2
    assert positions[0].open_time == 1
    assert positions[0].symbol == 'eth-btc'
    assert positions[1].open_time == 2
    assert positions[1].symbol == 'xmr-btc'


async def test_repick_symbols_does_not_repick_during_adjusted_start(mocker) -> None:
    informant = mocker.patch('juno.components.Informant', autospec=True)
    informant.get_fees_filters.return_value = (Fees(), Filters())
    informant.map_tickers.return_value = {
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    }
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1): [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
        ],
    })
    trader = traders.Multi(chandler=chandler, informant=informant)

    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=1,
        end=2,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(Fixed, maturity=2, advices=[Advice.NONE, Advice.NONE]),
        track_count=1,
        position_count=1,
        adjust_start=True,
    )
    state = await trader.initialize(config)

    await trader.run(state)

    # Initial call and repick during second candle.
    assert len(informant.map_tickers.mock_calls) == 2


async def test_repick_symbols_with_adjusted_start() -> None:
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    chandler = fakes.Chandler(future_candles={
        ('dummy', 'eth-btc', 1): [
            Candle(time=0, close=Decimal('1.0')),
            Candle(time=1, close=Decimal('1.0')),
        ],
        ('dummy', 'ltc-btc', 1): [
            Candle(time=1, close=Decimal('1.0')),
            Candle(time=2, close=Decimal('1.0')),
        ],
    })
    trader = traders.Multi(chandler=chandler, informant=informant)

    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=1,
        end=3,
        quote=Decimal('1.0'),
        strategy=TypeConstructor.from_type(Fixed, maturity=2, advices=[Advice.NONE, Advice.NONE]),
        symbol_strategies={
            'ltc-btc': TypeConstructor.from_type(
                Fixed,
                maturity=2,
                advices=[Advice.NONE, Advice.LONG],
            ),
        },
        track_count=1,
        position_count=1,
        close_on_exit=True,
        adjust_start=True,
    )
    state = await trader.initialize(config)
    informant.tickers = {
        'ltc-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    }

    summary = await trader.run(state)

    positions = summary.list_positions()
    assert len(positions) == 1
    assert positions[0].open_time == 3
    assert positions[0].symbol == 'ltc-btc'


async def test_rebalance_quotes() -> None:
    chandler = fakes.Chandler(
        candles={
            ('dummy', s, 1): [Candle(time=i, close=Decimal(f'{i + 1}.0')) for i in range(3)]
            for s in ['eth-btc', 'ltc-btc', 'xmr-btc']
        },
    )
    informant = fakes.Informant(tickers={
        'eth-btc': Ticker(
            volume=Decimal('3.0'),
            quote_volume=Decimal('3.0'),
            price=Decimal('1.0'),
        ),
        'ltc-btc': Ticker(
            volume=Decimal('2.0'),
            quote_volume=Decimal('2.0'),
            price=Decimal('1.0'),
        ),
        'xmr-btc': Ticker(
            volume=Decimal('1.0'),
            quote_volume=Decimal('1.0'),
            price=Decimal('1.0'),
        ),
    })
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.MultiConfig(
        exchange='dummy',
        interval=1,
        start=0,
        end=3,
        quote=Decimal('3.0'),
        strategy=TypeConstructor.from_type(Fixed),
        symbol_strategies={
            'eth-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LONG, Advice.NONE, Advice.LIQUIDATE],
            ),
            'ltc-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.LONG, Advice.LIQUIDATE, Advice.NONE],
            ),
            'xmr-btc': TypeConstructor.from_type(
                Fixed,
                advices=[Advice.NONE, Advice.NONE, Advice.NONE],
            ),
        },
        long=True,
        track_count=3,
        position_count=3,
        close_on_exit=True,
    )
    state = await trader.initialize(config)

    summary = await trader.run(state)

    # Quote distribution at the end of every tick:
    # 1.0 1.0 2.0
    # 1.0 1.5 2.0
    # 1.0 1.5 2.0

    assert len(summary.list_positions()) == 2
    assert state.quotes == [Decimal('2.0'), Decimal('2.0'), Decimal('2.0')]
