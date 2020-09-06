import asyncio
from decimal import Decimal

import pytest

from juno import Advice, Balance, Candle, Fill, OrderResult, OrderStatus, Ticker, traders
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

        if i < 3:  # If not last iteration, cancel, store and retrieve from storage.
            await cancel(trader_task)
            await storage.set('shard', 'key', trader_state)
            trader_state = await storage.get('shard', 'key', traders.Multi.State)

            # Change tickers for informant. This shouldn't crash the trader.
            informant.tickers.insert(
                0,
                Ticker(symbol='xmr-btc', volume=Decimal('3.0'), quote_volume=Decimal('3.0')),
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
        strategy=TypeConstructor.from_type(
            Fixed,
            advices=[Advice.LONG] * 10,
        ),
        long=True,
        short=True,
        track_count=2,
        position_count=2,
    )

    summary = await trader.run(config)

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
        stop_loss=Decimal('0.5'),
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

    summary = await trader.run(config)

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
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('2.0'), quote_volume=Decimal('2.0')),
        Ticker(symbol='ltc-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant)
    config = traders.Multi.Config(
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

    state = traders.Multi.State()
    trader_task = asyncio.create_task(trader.run(config, state))

    await asyncio.gather(
        *(chandler.future_candle_queues[('dummy', s, 1)].join() for s in symbols)
    )
    # Sleep to give control back to position manager.
    await asyncio.sleep(0)

    await cancel(trader_task)
    await storage.set('shard', 'key', state)
    state = await storage.get('shard', 'key', traders.Multi.State)
    chandler.future_candle_queues[('dummy', 'eth-btc', 1)].put_nowait(
        Candle(time=2, close=Decimal('30.0'))
    )
    chandler.future_candle_queues[('dummy', 'ltc-btc', 1)].put_nowait(
        Candle(time=2, close=Decimal('3.0'))
    )
    summary = await trader.run(config, state)

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
    wallet = mocker.patch('juno.components.wallet.Wallet')
    wallet.get_balance.return_value = Balance(Decimal('1.0'))
    broker = mocker.patch('juno.brokers.market.Market', autospec=True)
    broker.buy.return_value = OrderResult(
        time=0,
        status=OrderStatus.FILLED,
        fills=[Fill.with_computed_quote(price=Decimal('1.0'), size=Decimal('1.0'))],
    )

    chandler = fakes.Chandler(
        future_candles={('dummy', 'eth-btc', 1): [Candle(time=0, close=Decimal('1.0'))]},
    )
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    trader = traders.Multi(chandler=chandler, informant=informant, wallet=wallet, broker=broker)
    config = traders.Multi.Config(
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

    state = traders.Multi.State()
    trader_task = asyncio.create_task(trader.run(config, state))
    await chandler.future_candle_queues[('dummy', 'eth-btc', 1)].join()
    # Sleep to give control back to position manager.
    await asyncio.sleep(0)
    await cancel(trader_task)

    chandler.future_candle_queues[('dummy', 'eth-btc', 1)].put_nowait(
        Candle(time=1, close=Decimal('2.0'))
    )

    wallet.get_balance.return_value = Balance(Decimal('0.0'))
    await trader.run(config, state)


async def test_open_new_positions():
    informant = fakes.Informant(tickers=[
        Ticker(symbol='eth-btc', volume=Decimal('1.0'), quote_volume=Decimal('1.0')),
    ])
    chandler = fakes.Chandler(candles={
        ('dummy', 'eth-btc', 1): [Candle(time=0, close=Decimal('1.0'))]
    })
    trader = traders.Multi(chandler=chandler, informant=informant)

    config = traders.Multi.Config(
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
    state = traders.Multi.State(open_new_positions=False)
    summary = await trader.run(config, state)

    assert len(summary.list_positions()) == 0
