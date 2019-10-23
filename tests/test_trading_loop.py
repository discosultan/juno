from decimal import Decimal

from juno import Advice
from juno.trading import TradingLoop

from . import fakes
from .utils import new_candle


async def test_trailing_stop_loss():
    chandler = fakes.Chandler(
        candles=[
            new_candle(time=0, close=Decimal(10)),  # Buy.
            new_candle(time=1, close=Decimal(20)),
            new_candle(time=2, close=Decimal(18)),  # Trigger trailing stop (10%).
            new_candle(time=3, close=Decimal(10)),  # Sell (do not act).
        ]
    )
    loop = TradingLoop(
        chandler=chandler,
        informant=fakes.Informant(),
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal(10),
        new_strategy=lambda: fakes.Strategy(Advice.BUY, Advice.NONE, Advice.NONE, Advice.SELL),
        broker=None,
        test=True,
        restart_on_missed_candle=False,
        adjust_start=False,
        trailing_stop=Decimal('0.1'),
    )

    await loop.run()
    res = loop.summary

    assert res.profit == 8


async def test_restart_on_missed_candle():
    chandler = fakes.Chandler(
        candles=[
            new_candle(time=0),
            # 1 candle skipped.
            new_candle(time=2),  # Trigger restart.
            new_candle(time=3),
        ]
    )
    strategy1 = fakes.Strategy(Advice.NONE)
    strategy2 = fakes.Strategy(Advice.NONE, Advice.NONE, Advice.NONE)
    strategy_stack = [strategy2, strategy1]

    loop = TradingLoop(
        chandler=chandler,
        informant=fakes.Informant(),
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal(10),
        new_strategy=lambda: strategy_stack.pop(),
        restart_on_missed_candle=True,
        adjust_start=False,
        trailing_stop=Decimal(0),
    )

    await loop.run()

    assert len(strategy1.updates) == 1
    assert strategy1.updates[0].time == 0

    assert len(strategy2.updates) == 2
    assert strategy2.updates[0].time == 2
    assert strategy2.updates[1].time == 3
