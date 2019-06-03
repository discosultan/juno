from decimal import Decimal

from juno import Candle


def new_candle(time=0, close=Decimal(0), volume=Decimal(0)):
    return Candle(
        time=time,
        open=Decimal(0),
        high=Decimal(0),
        low=Decimal(0),
        close=close,
        volume=volume,
        closed=True)
