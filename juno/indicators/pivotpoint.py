from decimal import Decimal


class PivotPoint:
    value: Decimal = Decimal("0.0")
    support1: Decimal = Decimal("0.0")
    support2: Decimal = Decimal("0.0")
    resistance1: Decimal = Decimal("0.0")
    resistance2: Decimal = Decimal("0.0")

    @property
    def maturity(self) -> int:
        return 0

    @property
    def mature(self) -> bool:
        return True

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        raise NotImplementedError()
        diff = high - low
        self.value = (high + low + close) / 3
        self.support1 = 2 * self.value - high
        self.support2 = self.value - diff
        self.resistance1 = 2 * self.value - low
        self.resistance2 = self.value + diff
