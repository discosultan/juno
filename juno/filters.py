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
        # 0 means disabled.
        self.min = min_
        # 0 means disabled.
        self.max = max_
        # 0 means disabled.
        self.step = step

    def adjust(self, price: Decimal) -> Decimal:
        if price < self.min:
            return Decimal(0)
        if self.max:
            price = min(price, self.max)
        return price.quantize(self.step.normalize(), rounding=ROUND_FLOOR)

    def valid(self, price: Decimal) -> bool:
        return ((not self.min or price >= self.min) and
                (not self.max or price <= self.max) and
                (not self.step or (price - self.min) % self.step == 0))

    @staticmethod
    def none() -> Price:
        return Price()


class PercentPrice:

    def __init__(self, multiplier_up: Decimal, multiplier_down: Decimal, avg_price_period: int = 0
                 ) -> None:
        self.multiplier_up = multiplier_up
        self.multiplier_down = multiplier_down
        # 0 means the last price is used.
        self.avg_price_period = avg_price_period

    def valid(self, price: Decimal, weighted_average_price: Decimal) -> bool:
        return (price <= weighted_average_price * self.multiplier_up and
                price >= weighted_average_price * self.multiplier_down)

    @staticmethod
    def none() -> PercentPrice:
        return PercentPrice(multiplier_up=Decimal('Inf'), multiplier_down=Decimal(0))


class Size:

    def __init__(self, min_: Decimal, max_: Decimal, step: Decimal) -> None:
        self.min = min_
        self.max = max_
        self.step = step

    def adjust(self, size: Decimal) -> Decimal:
        if size < self.min:
            return Decimal(0)
        size = min(size, self.max)
        return size.quantize(self.step.normalize(), rounding=ROUND_DOWN)

    def valid(self, size: Decimal) -> bool:
        return (size >= self.min and
                size <= self.max and
                (size - self.min) % self.step == 0)

    @staticmethod
    def none() -> Size:
        return Size(min_=Decimal(0), max_=Decimal('Inf'), step=Decimal(0))


class MinNotional:

    def __init__(self, min_notional: Decimal, apply_to_market: bool, avg_price_period: int = 0
                 ) -> None:
        self.min_notional = min_notional
        self.apply_to_market = apply_to_market
        # 0 means the last price is used.
        self.avg_price_period = avg_price_period

    @staticmethod
    def none() -> MinNotional:
        return MinNotional(min_notional=Decimal(0), apply_to_market=False)


class Filters:

    def __init__(
            self,
            price: Price = Price.none(),
            percent_price: PercentPrice = PercentPrice.none(),
            size: Size = Size.none(),
            min_notional: MinNotional = MinNotional.none()) -> None:
        self.price = price
        self.percent_price = percent_price
        self.size = size
        self.min_notional = min_notional

    @staticmethod
    def none() -> Filters:
        return Filters(
            price=Price(),
            percent_price=PercentPrice.none(),
            size=Size.none(),
            min_notional=MinNotional.none())
