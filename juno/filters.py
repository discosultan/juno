# Exchange filters.
# https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#filters

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import NamedTuple


class Price(NamedTuple):
    min: Decimal = Decimal('0.0')  # 0 means disabled.
    max: Decimal = Decimal('0.0')  # 0 means disabled.
    step: Decimal = Decimal('0.0')  # 0 means disabled.

    def round_down(self, price: Decimal) -> Decimal:
        if price < self.min:
            return Decimal('0.0')
        if self.max:
            price = min(price, self.max)
        return price.quantize(self.step.normalize(), rounding=ROUND_DOWN)

    def valid(self, price: Decimal) -> bool:
        return ((not self.min or price >= self.min) and (not self.max or price <= self.max)
                and (not self.step or (price - self.min) % self.step == 0))

    @staticmethod
    def none() -> Price:
        return Price()


class PercentPrice(NamedTuple):
    multiplier_up: Decimal
    multiplier_down: Decimal
    avg_price_period: int = 0  # 0 means the last price is used.

    def valid(self, price: Decimal, weighted_average_price: Decimal) -> bool:
        return (
            price <= weighted_average_price * self.multiplier_up
            and price >= weighted_average_price * self.multiplier_down
        )

    @staticmethod
    def none() -> PercentPrice:
        return PercentPrice(multiplier_up=Decimal('Inf'), multiplier_down=Decimal('0.0'))


class Size(NamedTuple):
    min: Decimal
    max: Decimal
    step: Decimal

    def round_down(self, size: Decimal) -> Decimal:
        return self._round(size, ROUND_DOWN)

    def round_up(self, size: Decimal) -> Decimal:
        return self._round(size, ROUND_UP)

    def _round(self, size: Decimal, rounding: str) -> Decimal:
        if size < self.min:
            return Decimal('0.0')
        size = min(size, self.max)
        return size.quantize(self.step.normalize(), rounding=rounding)

    def valid(self, size: Decimal) -> bool:
        return (size >= self.min and size <= self.max and (size - self.min) % self.step == 0)

    @staticmethod
    def none() -> Size:
        return Size(min=Decimal('0.0'), max=Decimal('Inf'), step=Decimal('0.0'))


class MinNotional(NamedTuple):
    min_notional: Decimal
    apply_to_market: bool
    avg_price_period: int = 0  # 0 means the last price is used.

    def valid(self, price: Decimal, size: Decimal) -> bool:
        # For limit order only.
        return price * size >= self.min_notional

    def min_size_for_price(self, price: Decimal) -> Decimal:
        return self.min_notional / price

    @staticmethod
    def none() -> MinNotional:
        return MinNotional(min_notional=Decimal('0.0'), apply_to_market=False)


class Filters(NamedTuple):
    base_precision: int = 8
    quote_precision: int = 8

    price: Price = Price.none()
    percent_price: PercentPrice = PercentPrice.none()
    size: Size = Size.none()
    min_notional: MinNotional = MinNotional.none()

    @staticmethod
    def none() -> Filters:
        return Filters()
