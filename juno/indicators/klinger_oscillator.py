from decimal import Decimal


class KlingerOscillator:
    def __init__(self) -> None:
        self.value = Decimal('0.0')
        self._t = 0
        self._t1 = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, volume: Decimal, price: Decimal) -> None:
        raise NotImplementedError()
        self._t = min(self._t + 1, self._t1)
