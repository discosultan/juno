from decimal import Decimal
# TODO: Fix in 3.8.1
from typing import get_args, get_origin, get_type_hints  # type: ignore

from juno import Candle, Fill, Fills, Position


def new_candle(time=0, close=Decimal('0.0'), volume=Decimal('0.0'), closed=True):
    return Candle(
        time=time,
        open=Decimal('0.0'),
        high=Decimal('0.0'),
        low=Decimal('0.0'),
        close=close,
        volume=volume,
        closed=closed,
    )


def new_fill(price=Decimal('1.0'), size=Decimal('1.0'), fee=Decimal('0.0'), fee_asset='foo'):
    return Fill(
        price=price,
        size=size,
        fee=fee,
        fee_asset=fee_asset,
    )


def new_closed_position(profit):
    size = abs(profit)
    price = Decimal('1.0') if profit >= 0 else Decimal('-1.0')
    pos = Position(time=0, fills=Fills([new_fill(price=Decimal('0.0'), size=size)]))
    pos.close(time=1, fills=Fills([new_fill(price=price, size=size)]))
    return pos


def types_match(obj, type_=None):
    if type_ is None:
        # Works only for named tuples.
        type_ = type(obj)

    if isinstance(obj, tuple):
        field_types = get_type_hints(type_).values()
        return all((isinstance(obj[i], get_origin(t) or t) for i, t in enumerate(field_types)))
    elif isinstance(obj, dict):
        key_type, value_type = get_args(type_)
        for k, v in obj.items():
            if not isinstance(k, key_type) or not isinstance(v, value_type):
                return False
        return True
    else:
        raise NotImplementedError(f'Type matching not implemented for {type_}')
