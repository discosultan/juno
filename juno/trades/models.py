from decimal import Decimal
from typing import NamedTuple


class Trade(NamedTuple):
    id: int = 0  # Aggregate trade id.
    time: int = 0  # Can have multiple trades at same time.
    price: Decimal = Decimal('0.0')
    size: Decimal = Decimal('0.0')

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            'time': 'index',
        }
