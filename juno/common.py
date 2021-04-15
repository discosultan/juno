from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import NamedTuple, Optional, Union

from juno.aliases import Timestamp
from juno.math import round_down, round_half_up


class Advice(IntEnum):
    NONE = 0
    LONG = 1
    SHORT = 2
    LIQUIDATE = 3

    @staticmethod
    def combine(*advices: Advice) -> Advice:
        if len(advices) == 0 or any(a is Advice.NONE for a in advices):
            return Advice.NONE
        if len(set(advices)) == 1:
            return advices[0]
        return Advice.LIQUIDATE


class Balance(NamedTuple):
    available: Decimal = Decimal('0.0')
    # TODO: Do we need it? Kraken doesn't provide that data, for example.
    hold: Decimal = Decimal('0.0')
    # Margin account related. Binance doesn't provide this through websocket!
    borrowed: Decimal = Decimal('0.0')
    interest: Decimal = Decimal('0.0')

    @property
    def repay(self) -> Decimal:
        return self.borrowed + self.interest

    @property
    def significant(self) -> bool:
        return (
            self.available > 0
            or self.hold > 0
            or self.borrowed > 0
            or self.interest > 0
        )


class MissedCandlePolicy(IntEnum):
    IGNORE = 0
    RESTART = 1
    LAST = 2
