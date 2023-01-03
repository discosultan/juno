# Exchange filters.
# https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#filters

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from juno.errors import BadOrder
from juno.math import round_half_up


@dataclass(frozen=True)
class Price:
    min: Decimal = Decimal("0.0")
    max: Decimal = Decimal("0.0")  # 0 means disabled.
    step: Decimal = Decimal("0.0")  # 0 means disabled.

    def round_down(self, price: Decimal) -> Decimal:
        if price < self.min:
            return Decimal("0.0")

        if self.max > 0:
            price = min(price, self.max)
        if self.step > 0:
            price = price.quantize(self.step.normalize(), rounding=ROUND_DOWN)

        return price

    def valid(self, price: Decimal) -> bool:
        return (
            price >= self.min
            and (not self.max or price <= self.max)
            and (not self.step or price % self.step == 0)
        )


@dataclass(frozen=True)
class PercentPrice:
    multiplier_up: Decimal = Decimal("0.0")  # 0 means disabled.
    multiplier_down: Decimal = Decimal("0.0")
    avg_price_period: int = 0  # 0 means the last price is used.

    def valid(self, price: Decimal, weighted_average_price: Decimal) -> bool:
        return (
            not self.multiplier_up or price <= weighted_average_price * self.multiplier_up
        ) and price >= weighted_average_price * self.multiplier_down


@dataclass(frozen=True)
class PercentPriceBySide:
    bid_multiplier_up: Decimal = Decimal("0.0")  # 0 means disabled.
    bid_multiplier_down: Decimal = Decimal("0.0")
    ask_multiplier_up: Decimal = Decimal("0.0")  # 0 means disabled.
    ask_multiplier_down: Decimal = Decimal("0.0")
    avg_price_period: int = 0  # 0 means the last price is used.

    def valid_bid(self, price: Decimal, weighted_average_price: Decimal) -> bool:
        return (
            not self.bid_multiplier_up or price <= weighted_average_price * self.bid_multiplier_up
        ) and price >= weighted_average_price * self.bid_multiplier_down

    def valid_ask(self, price: Decimal, weighted_average_price: Decimal) -> bool:
        return (
            not self.ask_multiplier_up or price <= weighted_average_price * self.ask_multiplier_up
        ) and price >= weighted_average_price * self.ask_multiplier_down


@dataclass(frozen=True)
class Size:
    min: Decimal = Decimal("0.0")
    max: Decimal = Decimal("0.0")  # 0 means disabled.
    step: Decimal = Decimal("0.0")  # 0 means disabled.

    def round_down(self, size: Decimal) -> Decimal:
        return self._round(size, ROUND_DOWN)

    def round_up(self, size: Decimal) -> Decimal:
        return self._round(size, ROUND_UP)

    def _round(self, size: Decimal, rounding: str) -> Decimal:
        if size < self.min:
            return Decimal("0.0")

        if self.max > 0:
            size = min(size, self.max)
        if self.step > 0:
            size = size.quantize(self.step.normalize(), rounding=rounding)

        return size

    def valid(self, size: Decimal) -> bool:
        return (
            size >= self.min
            and (not self.max or size <= self.max)
            and (not self.step or (size - self.min) % self.step == 0)
        )

    def validate(self, size: Decimal) -> None:
        if not self.valid(size):
            raise BadOrder(
                f"Size {size} must be between [{self.min}; {self.max}] with a step of {self.step}"
            )


@dataclass(frozen=True)
class MinNotional:
    min_notional: Decimal = Decimal("0.0")
    apply_to_market: bool = False
    avg_price_period: int = 0  # 0 means the last price is used.

    def valid(self, price: Decimal, size: Decimal) -> bool:
        # For limit order only.
        return price * size >= self.min_notional

    def min_size_for_price(self, price: Decimal) -> Decimal:
        return self.min_notional / price

    def validate_limit(self, price: Decimal, size: Decimal) -> None:
        if not self.valid(price, size):
            raise BadOrder(
                f"Price {price} * size {size} ({price * size}) must be between "
                f"[{self.min_notional}; inf]"
            )

    def validate_market(self, avg_price: Decimal, size: Decimal) -> None:
        if self.apply_to_market:
            self.validate_limit(avg_price, size)


@dataclass(frozen=True)
class Filters:
    price: Price = field(default_factory=Price)
    percent_price: PercentPrice = field(default_factory=PercentPrice)
    percent_price_by_side: PercentPriceBySide = field(default_factory=PercentPriceBySide)
    size: Size = field(default_factory=Size)
    min_notional: MinNotional = field(default_factory=MinNotional)

    base_precision: int = 8
    quote_precision: int = 8
    spot: bool = True
    cross_margin: bool = False
    isolated_margin: bool = False

    def with_fee(self, size: Decimal, fee_rate: Decimal) -> Decimal:
        fee = round_half_up(size * fee_rate, self.base_precision)
        return self.size.round_up(size + fee)

    def min_size(self, price: Decimal) -> Decimal:
        size = self.min_notional.min_size_for_price(price)
        return self.size.round_down(size) if size > self.size.min else self.size.round_up(size)
