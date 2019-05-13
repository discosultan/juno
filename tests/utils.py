from decimal import Decimal
from os import path
from typing import Any, Dict

import simplejson as json

from juno import Candle


def full_path(rel_path: str) -> str:
    return path.join(path.dirname(__file__), *filter(None, rel_path.split('/')))


def load_json_file(rel_path: str) -> Dict[str, Any]:
    with open(full_path(rel_path)) as f:
        return json.load(f, use_decimal=True)


def new_candle(time=0, close=Decimal(0), volume=Decimal(0)):
    return Candle(
        time=time,
        open=Decimal(0),
        high=Decimal(0),
        low=Decimal(0),
        close=close,
        volume=volume,
        closed=True)
