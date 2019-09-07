from decimal import Decimal

from juno import Candle, Fill, Fills, Position


def new_candle(time=0, close=Decimal(0), volume=Decimal(0), closed=True):
    return Candle(
        time=time,
        open=Decimal(0),
        high=Decimal(0),
        low=Decimal(0),
        close=close,
        volume=volume,
        closed=closed,
    )


def new_fill(price=Decimal(1), size=Decimal(1), fee=Decimal(0), fee_asset='foo'):
    return Fill(
        price=price,
        size=size,
        fee=fee,
        fee_asset=fee_asset,
    )


def new_closed_position(profit):
    size = abs(profit)
    price = Decimal(1) if profit >= 0 else Decimal(-1)
    pos = Position(time=0, fills=Fills([new_fill(price=0, size=size)]))
    pos.close(time=1, fills=Fills([new_fill(price=price, size=size)]))
    return pos
