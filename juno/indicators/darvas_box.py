from collections import deque
from decimal import Decimal


class DarvasBox:
    top_box: Decimal = Decimal("0.0")
    bottom_box: Decimal = Decimal("0.0")

    _boxp: int

    _previous_k1: Decimal = Decimal("inf")
    _ll_deque: deque[Decimal]
    _k1_deque: deque[Decimal]
    _k2_deque: deque[Decimal]
    _k3_deque: deque[Decimal]
    _bars_since_high_gt_previous_k1: int = 0
    _nh: Decimal = Decimal("0.0")

    _t: int = 0

    def __init__(self, boxp: int = 5) -> None:
        if boxp < 2:
            raise ValueError("Length cannot be less than 2")

        self._boxp = boxp
        self._ll_deque = deque(maxlen=boxp)
        self._k1_deque = deque(maxlen=boxp)
        self._k2_deque = deque(maxlen=boxp - 1)
        self._k3_deque = deque(maxlen=boxp - 2)

    @property
    def maturity(self) -> int:
        return self._boxp

    @property
    def mature(self) -> bool:
        return self._t >= self._boxp

    def update(self, high: Decimal, low: Decimal) -> tuple[Decimal, Decimal]:
        self._t = min(self._t + 1, self._boxp)

        self._ll_deque.append(low)
        self._k1_deque.append(high)
        self._k2_deque.append(high)
        self._k3_deque.append(high)

        ll = min(self._ll_deque, default=Decimal("0.0"))
        k1 = max(self._k1_deque, default=Decimal("0.0"))
        k2 = max(self._k2_deque, default=Decimal("0.0"))
        k3 = max(self._k3_deque, default=Decimal("0.0"))

        if high > self._previous_k1:
            self._nh = high

        self._bars_since_high_gt_previous_k1 = (
            0 if high > self._previous_k1 else self._bars_since_high_gt_previous_k1 + 1
        )

        if self._bars_since_high_gt_previous_k1 == self._boxp - 2 and k3 < k2:
            self.top_box = self._nh
            self.bottom_box = ll

        self._previous_k1 = k1
        return self.top_box, self.bottom_box
