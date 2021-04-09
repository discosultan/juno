from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import NamedTuple, Optional, Union

from juno.math import round_down, round_half_up


class Depth(ModuleType):
    class Snapshot(NamedTuple):
        bids: list[tuple[Decimal, Decimal]] = []
        asks: list[tuple[Decimal, Decimal]] = []
        last_id: int = 0

    class Update(NamedTuple):
        bids: list[tuple[Decimal, Decimal]] = []
        asks: list[tuple[Decimal, Decimal]] = []
        first_id: int = 0
        last_id: int = 0

    Any = Union[Snapshot, Update]


class Fill(NamedTuple):
    price: Decimal = Decimal('0.0')
    size: Decimal = Decimal('0.0')
    quote: Decimal = Decimal('0.0')
    fee: Decimal = Decimal('0.0')
    fee_asset: str = 'btc'

    @staticmethod
    def with_computed_quote(
        price: Decimal,
        size: Decimal,
        fee: Decimal = Decimal('0.0'),
        fee_asset: str = 'btc',
        precision: Optional[int] = None,
    ) -> Fill:
        quote = price * size
        return Fill(
            price=price,
            size=size,
            quote=round_down(quote, precision) if precision is not None else quote,
            fee=fee,
            fee_asset=fee_asset,
        )

    @staticmethod
    def mean_price(fills: list[Fill]) -> Decimal:
        total_size = Fill.total_size(fills)
        return sum((f.price * f.size / total_size for f in fills), Decimal('0.0'))

    @staticmethod
    def total_size(fills: list[Fill]) -> Decimal:
        return sum((f.size for f in fills), Decimal('0.0'))

    @staticmethod
    def total_quote(fills: list[Fill]) -> Decimal:
        return sum((f.quote for f in fills), Decimal('0.0'))

    @staticmethod
    def total_fee(fills: list[Fill], asset: str) -> Decimal:
        return sum((f.fee for f in fills if f.fee_asset == asset), Decimal('0.0'))

    @staticmethod
    def all_fees(fills: list[Fill]) -> dict[str, Decimal]:
        res: dict[str, Decimal] = defaultdict(lambda: Decimal('0.0'))
        for fill in fills:
            res[fill.fee_asset] += fill.fee
        return dict(res)

    @staticmethod
    def expected_quote(fills: list[Fill], precision: int) -> Decimal:
        return sum(
            (round_down(f.price * f.size, precision) for f in fills),
            Decimal('0.0'),
        )

    @staticmethod
    def expected_base_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )

    @staticmethod
    def expected_quote_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * f.price * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )


class Side(IntEnum):
    BUY = 0
    SELL = 1
