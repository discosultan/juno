from decimal import Decimal

from .rsi import Rsi


# Stochastic Relative Strength Index
class StochRsi:

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f'invalid period ({period})')

        self.rsi = Rsi(period)
        self.t = 0
        self.t1 = period
        self.t2 = period * 2 - 1
        self.min = Decimal(0)
        self.max = Decimal(0)
        self.rsi_values = _Buffer(period)

    @property
    def req_history(self) -> int:
        return self.t2

    def update(self, price: Decimal) -> Decimal:
        result = self.rsi.update(price)

        if self.t >= self.t1:
            self.rsi_values.qpush(result)

        if self.t == self.t2:
            self.min = min(self.rsi_values.vals)
            self.max = max(self.rsi_values.vals)
            diff = self.max - self.min
            if diff == Decimal(0):
                result = Decimal(0)
            else:
                result = (result - self.min) / diff
            print(result)
        else:
            result = Decimal(0)

        self.last_input = price
        self.t = min(self.t + 1, self.t2)
        return result


class _Buffer:

    def __init__(self, size: int) -> None:
        self.vals = [Decimal(0)] * size
        self.pushes = 0
        self.index = 0
        self.sum = Decimal(0)

    def __len__(self) -> int:
        return len(self.vals)

    def push(self, val: Decimal) -> None:
        if self.pushes >= len(self.vals):
            self.sum -= self.vals[self.index]

        self.sum += val
        self.vals[self.index] = val
        self.pushes += 1
        self.index += 1
        if self.index >= len(self.vals):
            self.index = 0

    def qpush(self, val: Decimal) -> None:
        self.vals[self.index] = val
        self.index += 1
        if self.index >= len(self.vals):
            self.index = 0
