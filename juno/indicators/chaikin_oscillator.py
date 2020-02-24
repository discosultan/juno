from decimal import Decimal


class ChaikinOscillator:
    def __init__(self, short_period: int, long_period: int) -> None:
        self.value = Decimal('0.0')
        self._t = 0
        self._t1 = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, high: Decimal, low: Decimal, close: Decimal, volume: Decimal) -> None:
        raise NotImplementedError()
        self._t = min(self._t + 1, self._t1)
