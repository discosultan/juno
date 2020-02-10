from decimal import Decimal

import pytest

from juno import Advice, Candle, Fill
from juno.trading import MissedCandlePolicy, Position, Trader, TradingResult

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
    result = TradingResult(start=0, quote=Decimal('100.0'))
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
        result.append_position(position)

    assert result.cost == Decimal('100.0')
    assert result.gain == Decimal('102.91')
    assert result.profit == Decimal('2.91')
    assert result.max_drawdown == pytest.approx(Decimal('0.1495'), Decimal('0.001'))


def test_empty_trading_summary() -> None:
    result = TradingResult(start=0, quote=Decimal('100.0'))
    assert result.cost == 100
    assert result.gain == 100
    assert result.profit == 0
    assert result.max_drawdown == 0


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
    trader = Trader(
        chandler=chandler,
        informant=fakes.Informant(),
    )

    start = 0
    quote = Decimal('10.0')
    result = TradingResult(start=start, quote=quote)
    await trader.run(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=start,
        end=4,
        quote=quote,
        new_strategy=lambda: fakes.Strategy(Advice.BUY, None, None, Advice.SELL),
        missed_candle_policy=MissedCandlePolicy.IGNORE,
        adjust_start=False,
        trailing_stop=Decimal('0.1'),
        result=result
    )

    assert result.profit == 8


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
    trader = Trader(
        chandler=chandler,
        informant=fakes.Informant(),
    )
    strategy1 = fakes.Strategy(None, None)
    strategy2 = fakes.Strategy(None, None, None)
    strategy_stack = [strategy2, strategy1]

    start = 0
    quote = Decimal('10.0')
    result = TradingResult(start=start, quote=quote)
    await trader.run(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=start,
        end=6,
        quote=quote,
        new_strategy=lambda: strategy_stack.pop(),
        missed_candle_policy=MissedCandlePolicy.RESTART,
        adjust_start=False,
        trailing_stop=Decimal('0.0'),
        result=result
    )

    assert len(strategy1.updates) == 2
    assert strategy1.updates[0].time == 0
    assert strategy1.updates[1].time == 1

    assert len(strategy2.updates) == 3
    assert strategy2.updates[0].time == 3
    assert strategy2.updates[1].time == 4
    assert strategy2.updates[2].time == 5


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
    trader = Trader(
        chandler=chandler,
        informant=fakes.Informant()
    )
    strategy = fakes.Strategy(None, None, None, None, None)

    start = 0
    quote = Decimal('10.0')
    result = TradingResult(start=start, quote=quote)
    await trader.run(
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=start,
        end=5,
        quote=quote,
        new_strategy=lambda: strategy,
        missed_candle_policy=MissedCandlePolicy.LAST,
        adjust_start=False,
        trailing_stop=Decimal('0.0'),
        result=result
    )

    assert len(strategy.updates) == 5
    assert strategy.updates[0].time == 0
    assert strategy.updates[1].time == 1
    assert strategy.updates[2].time == 2
    assert strategy.updates[3].time == 3
    assert strategy.updates[4].time == 4


def new_closed_position(profit: Decimal) -> Position:
    size = abs(profit)
    price = Decimal('1.0') if profit >= 0 else Decimal('-1.0')
    pos = Position(
        symbol='eth-btc',
        time=0,
        fills=[Fill(price=Decimal('0.0'), size=size)]
    )
    pos.close(time=1, fills=[Fill(price=price, size=size)])
    return pos
