from dataclasses import dataclass, field
from decimal import Decimal

from .filters import Filters


@dataclass
class AssetInfo:
    precision: int = 8


@dataclass
class BorrowInfo:
    daily_interest_rate: Decimal = Decimal('0.0')
    limit: Decimal = Decimal('0.0')

    @property
    def hourly_interest_rate(self) -> Decimal:
        return self.daily_interest_rate / 24


@dataclass
class Fees:
    maker: Decimal = Decimal('0.0')
    taker: Decimal = Decimal('0.0')


@dataclass
class ExchangeInfo:
    # Key: asset
    assets: dict[str, AssetInfo] = field(default_factory=lambda: {'__all__': AssetInfo()})
    # Key: symbol
    fees: dict[str, Fees] = field(default_factory=lambda: {'__all__': Fees()})
    # Key: symbol
    filters: dict[str, Filters] = field(default_factory=lambda: {'__all__': Filters()})
    # Keys: account, asset
    borrow_info: dict[str, dict[str, BorrowInfo]] = field(
        default_factory=lambda: {'__all__': {'__all__': BorrowInfo()}}
    )
