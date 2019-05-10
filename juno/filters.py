# Exchange filters.
# https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#filters

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal


class Price:

    def __init__(
            self,
            min_: Decimal = Decimal(0),
            max_: Decimal = Decimal(0),
            step: Decimal = Decimal(0)) -> None:
        self.min = min_
        self.max = max_
        self.step = step

    def adjust(self, price: Decimal) -> Decimal:
        if price < self.min:
            return Decimal(0)
        price = min(price, self.max)
        return price.quantize(self.step.normalize(), rounding=ROUND_FLOOR)


class Size:

    def __init__(
            self,
            min_: Decimal = Decimal(0),
            max_: Decimal = Decimal(0),
            step: Decimal = Decimal(0)) -> None:
        self.min = min_
        self.max = max_
        self.step = step

    def adjust(self, size: Decimal) -> Decimal:
        if size < self.min:
            return Decimal(0)
        size = min(size, self.max)
        return size.quantize(self.step.normalize(), rounding=ROUND_DOWN)


class Filters:

    def __init__(self, price: Price, size: Size) -> None:
        self.price = price
        self.size = size

    @staticmethod
    def none() -> Filters:
        return Filters(price=Price(), size=Size())
