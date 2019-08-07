from decimal import Decimal
from typing import Generic, List, Type, TypeVar

T = TypeVar('T', float, Decimal)


# Simple Moving Average
class Sma(Generic[T]):
    # TODO: Bug in mypy: https://github.com/python/mypy/issues/4236
    def __init__(self, period: int, dec: Type[T] = Decimal) -> None:  # type: ignore
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value: T = dec(0)
        self._inputs: List[T] = [dec(0)] * period
        self._i = 0
        self._sum: T = dec(0)
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: T) -> None:
        last = self._inputs[self._i]
        self._inputs[self._i] = price
        self._i = (self._i + 1) % len(self._inputs)
        self._sum = self._sum - last + price
        self.value = self._sum / len(self._inputs)

        self._t = min(self._t + 1, self._t1)
