from decimal import Decimal
from typing import NamedTuple


class Ticker(NamedTuple):
    volume: Decimal  # 24h.
    quote_volume: Decimal  # 24h.
    price: Decimal  # Last.
