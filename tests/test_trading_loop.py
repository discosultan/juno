from decimal import Decimal

from juno import Advice, Fees
from juno.filters import Filters, Price, Size
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
    informant = fakes.Informant(
        fees=Fees(Decimal(0), Decimal(0)),
        filters=Filters(
            price=Price(min=Decimal(1), max=Decimal(10000), step=Decimal(1)),
            size=Size(min=Decimal(1), max=Decimal(10000), step=Decimal(1))
        )
    )

    def new_strategy():
        return fakes.Strategy(Advice.BUY, Advice.NONE, Advice.NONE, Advice.SELL)

    loop = TradingLoop(
        chandler=chandler,
        informant=informant,
        exchange='dummy',
        symbol='eth-btc',
        interval=1,
        start=0,
        end=4,
        quote=Decimal(10),
        new_strategy=new_strategy,
        broker=None,
        test=True,
        restart_on_missed_candle=False,
        adjust_start=False,
        trailing_stop=Decimal('0.1'),
    )
    await loop.run()
    res = loop.summary

    assert res.profit == 8
