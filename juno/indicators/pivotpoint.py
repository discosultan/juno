from decimal import Decimal


class PivotPoint:

    def __init__(self) -> None:
        pass

    @property
    def req_history(self) -> int:
        return 0

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        diff = high - low
        self.value = (high + low + close) / 3
        self.support1 = 2 * self.value - high
        self.support2 = self.value - diff
        self.resistance1 = 2 * self.value - low
        self.resistance2 = self.value + diff
