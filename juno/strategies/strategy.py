from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional, Union

from juno import Advice, Candle
from juno.common import CandleMeta
from juno.constraints import Choice, Constraint
from juno.indicators import Alma, Dema, Ema, Ema2, Kama, Sma, Smma


class MidTrendPolicy(IntEnum):
    CURRENT = 0  # Will not skip on-going trend. Advice effective immediately.
    PREVIOUS = 1  # ?
    IGNORE = 2  # Will skip advice for on-going trend. Needs to see a new trend starting.


ma_choices = Choice([i.__name__.lower() for i in [Alma, Dema, Ema, Ema2, Kama, Sma, Smma]])
mid_trend_policy_choices = Choice(
    [
        MidTrendPolicy.CURRENT,
        MidTrendPolicy.PREVIOUS,
        MidTrendPolicy.IGNORE,
    ]
)


class Maturity:
    """Ignore advice if strategy not mature."""

    _maturity: int
    _age: int = 0

    def __init__(self, maturity: int) -> None:
        self._maturity = maturity

    @property
    def maturity(self) -> int:
        return self._maturity

    def update(self, value: Advice) -> Advice:
        result = Advice.NONE
        if self._age >= self._maturity - 1:
            result = value

        self._age = min(self._age + 1, self._maturity)
        return result


class MidTrend:
    """Ignore first advice if middle of trend."""

    _policy: MidTrendPolicy
    _previous: Optional[Advice] = None
    _enabled: bool = True

    def __init__(self, policy: MidTrendPolicy) -> None:
        self._policy = policy

    @property
    def maturity(self) -> int:
        return 1 if self._policy is MidTrendPolicy.CURRENT else 2

    def update(self, value: Advice) -> Advice:
        if not self._enabled or self._policy is not MidTrendPolicy.IGNORE:
            return value

        result = Advice.NONE
        if self._previous is None:
            self._previous = value
        elif value != self._previous:
            self._enabled = False
            result = value
        return result


class Persistence:
    """The number of ticks required to confirm an advice."""

    _age: int = 0
    _level: int
    _return_previous: bool
    _potential: Advice = Advice.NONE
    _previous: Advice = Advice.NONE

    def __init__(self, level: int, return_previous: bool = False) -> None:
        assert level >= 0

        self._level = level
        self._return_previous = return_previous

    @property
    def maturity(self) -> int:
        return self._level + 1

    def update(self, value: Advice) -> Advice:
        if self._level == 0:
            return value

        if value is not self._potential:
            self._age = 0
            self._potential = value

        if self._age >= self._level:
            self._previous = self._potential
            result = self._potential
        elif self._return_previous:
            result = self._previous
        else:
            result = Advice.NONE

        self._age = min(self._age + 1, self._level)

        return result


class Changed:
    """Pass an advice only if was changed on current tick."""

    _enabled: bool
    _previous: Advice = Advice.NONE
    _age: int = 0

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def prevailing_advice(self) -> Advice:
        return self._previous

    @property
    def prevailing_advice_age(self) -> int:
        return self._age

    @property
    def maturity(self) -> int:
        return 1

    def update(self, value: Advice) -> Advice:
        if not self._enabled:
            return value

        if value is Advice.NONE or value is self._previous:
            self._age += 1
            result = Advice.NONE
        else:
            self._previous = value
            self._age = 1
            result = value
        return result


class Strategy(ABC):
    @dataclass(frozen=True)
    class Meta:
        constraints: dict[Union[str, tuple[str, ...]], Constraint] = field(default_factory=dict)

    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta()

    @property
    @abstractmethod
    def maturity(self) -> int:
        pass

    @property
    @abstractmethod
    def mature(self) -> bool:
        pass

    @property
    def extra_candles(self) -> list[CandleMeta]:
        return []

    @abstractmethod
    def update(self, candle: Candle, meta: CandleMeta) -> None:
        pass

    @staticmethod
    def validate_constraints(type_: type[Strategy], *args: Any) -> None:
        # Assumes ordered.
        from_index = 0
        for names, constraint in type_.meta().constraints.items():
            # Normalize scalars into a single element tuples.
            if not isinstance(names, tuple):
                names = (names,)

            to_index = from_index + len(names)
            inputs = args[from_index:to_index]

            if not constraint.validate(*inputs):
                raise ValueError(
                    f'Incorrect argument(s): {",".join(map(str, inputs))} for parameter(s): '
                    f'{",".join(names)}'
                )

            from_index = to_index


class Signal(Strategy):
    @property
    @abstractmethod
    def advice(self) -> Advice:
        pass


class Oscillator(Strategy):
    @property
    @abstractmethod
    def overbought(self) -> bool:
        pass

    @property
    @abstractmethod
    def oversold(self) -> bool:
        pass
