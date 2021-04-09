from decimal import Decimal
from typing import NamedTuple

from juno.aliases import Timestamp
from juno.time import datetime_utcfromtimestamp_ms


# We have a choice between dataclasses and namedtuples. Namedtuples are chosen as they support
# iterating over values of an instance (i.e `*mytuple`) which is convenient for decomposing
# values for SQLite insertion. Dataclasses miss that functionality but offer comparisons, etc.
# out of the box.
class Candle(NamedTuple):
    time: Timestamp = 0  # Interval start time.
    open: Decimal = Decimal('0.0')
    high: Decimal = Decimal('0.0')
    low: Decimal = Decimal('0.0')
    close: Decimal = Decimal('0.0')
    volume: Decimal = Decimal('0.0')  # Within interval.
    closed: bool = True

    @property
    def midpoint(self) -> Decimal:
        return (self.open + self.close) / 2

    @property
    def mean_hlc(self) -> Decimal:
        return (self.high + self.low + self.close) / 3

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(time={datetime_utcfromtimestamp_ms(self.time)}, '
            f'open={self.open}, high={self.high}, low={self.low}, close={self.close}, '
            f'volume={self.volume}, closed={self.closed})'
        )

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            'time': 'unique',
        }
