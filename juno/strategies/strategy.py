from enum import IntEnum
from typing import Any, Dict, Optional, Tuple, Union

from juno import Advice, Candle
from juno.constraints import Choice, Constraint
from juno.indicators import Alma, Dema, Ema, Ema2, Kama, Sma, Smma


class MidTrendPolicy(IntEnum):
    CURRENT = 0
    PREVIOUS = 1
    IGNORE = 2


ma_choices = Choice([i.__name__.lower() for i in [Alma, Dema, Ema, Ema2, Kama, Sma, Smma]])
mid_trend_policy_choices = Choice([
    MidTrendPolicy.CURRENT,
    MidTrendPolicy.PREVIOUS,
    MidTrendPolicy.IGNORE,
])

# class Maturity:
#     """Ignore advice if strategy not mature."""
#     _maturity: int
#     _age: int = 0

#     def __init__(self, maturity: int) -> None:
#         self._maturity = maturity

#     @property
#     def maturity(self) -> int:
#         return self._maturity

#     def update(self, value: Advice) -> Advice:
#         result = Advice.NONE
#         if self._age >= self._maturity:
#             result = value

#         self._age = min(self._age + 1, self._maturity)
#         return result


class MidTrend:
    """Ignore first advice if middle of trend."""
    _policy: MidTrendPolicy
    _previous: Optional[Advice] = None
    _enabled: bool = True

    def __init__(self, policy: MidTrendPolicy) -> None:
        self._policy = policy

    @property
    def maturity(self) -> int:
        return 0 if self._policy is MidTrendPolicy.CURRENT else 1

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
        return self._level

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
    _previous: Advice = Advice.NONE
    _enabled: bool
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
        return 0

    def update(self, value: Advice) -> Advice:
        if not self._enabled:
            return value

        if value is self._previous:
            result = Advice.NONE
        else:
            self._age = 0
            result = value
        self._previous = value
        self._age += 1
        return result


class Meta:
    def __init__(
        self,
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
    ) -> None:
        self.constraints = constraints


class Strategy:
    advice: Advice = Advice.NONE
    maturity: int

    _t: int = -1

    # _maturity_filter: Maturity
    _mid_trend_filter: MidTrend
    _persistence_filter: Persistence

    _last_candle_time: int = -1

    @staticmethod
    def meta() -> Meta:
        return Meta()

    @property
    def adjust_hint(self) -> int:
        return (
            self.maturity
            + max(self._mid_trend_filter.maturity, self._persistence_filter.maturity)
        )

    def __init__(
        self,
        maturity: int = 0,
        mid_trend_policy: MidTrendPolicy = MidTrendPolicy.CURRENT,
        persistence: int = 0,
    ) -> None:
        self.maturity = maturity

        # self._maturity_filter = Maturity(maturity=maturity)
        self._mid_trend_filter = MidTrend(policy=mid_trend_policy)
        self._persistence_filter = Persistence(level=persistence)

    @property
    def mature(self) -> bool:
        return self._t >= self.maturity

    def update(self, candle: Candle) -> Advice:
        assert candle.time > self._last_candle_time

        self._t = min(self._t + 1, self.maturity)
        advice = self.tick(candle)

        if self.mature:
            advice = Advice.combine(
                self._mid_trend_filter.update(advice),
                self._persistence_filter.update(advice),
            )
        else:
            assert advice is Advice.NONE

        self.advice = advice
        self._last_candle_time = candle.time
        return advice

    def tick(self, candle: Candle) -> Advice:
        return Advice.NONE

    def validate(self, *args: Any) -> None:
        # Assumes ordered.
        from_index = 0
        for names, constraint in type(self).meta().constraints.items():
            # Normalize scalars into a single element tuples.
            if not isinstance(names, tuple):
                names = names,

            to_index = from_index + len(names)
            inputs = args[from_index:to_index]

            if not constraint.validate(*inputs):
                raise ValueError(
                    f'Incorrect argument(s): {",".join(map(str, inputs))} for parameter(s): '
                    f'{",".join(names)}'
                )

            from_index = to_index
