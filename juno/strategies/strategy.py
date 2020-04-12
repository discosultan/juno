from typing import Any, Dict, Optional, Tuple, Union

from juno import Advice, Candle
from juno.math import Constraint

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
    _ignore: bool
    _previous: Optional[Advice] = None
    _maturity: int

    def __init__(self, ignore: bool) -> None:
        self._ignore = ignore
        self._maturity = 1 if ignore else 0

    @property
    def maturity(self) -> int:
        return self._maturity

    def update(self, value: Advice) -> Advice:
        if not self._ignore:
            return value

        result = Advice.NONE
        if self._previous is None:
            self._previous = value
        elif value != self._previous:
            self._ignore = False
            result = value
        return result


class Persistence:
    """The number of ticks required to confirm an advice."""
    _age: int = 0
    _level: int
    _potential: Advice = Advice.NONE
    _previous: Advice = Advice.NONE

    def __init__(self, level: int) -> None:
        assert level >= 0
        self._level = level

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
            result = self._potential
            self._previous = result
        else:
            result = self._previous

        self._age = min(self._age + 1, self._level)

        return result


class Changed:
    """Pass an advice only if was changed on current tick."""
    _previous: Advice = Advice.NONE
    _enabled: bool

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def maturity(self) -> int:
        return 0

    def update(self, value: Advice) -> Advice:
        if not self._enabled:
            return value

        result = value if value is not self._previous else Advice.NONE
        self._previous = value
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

    _age: int = 0

    # _maturity_filter: Maturity
    _mid_trend_filter: MidTrend
    _persistence_filter: Persistence
    _changed_filter: Changed

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
        ignore_mid_trend: bool = False,
        persistence: int = 0,
    ) -> None:
        self.maturity = maturity

        # self._maturity_filter = Maturity(maturity=maturity)
        self._mid_trend_filter = MidTrend(ignore=ignore_mid_trend)
        self._persistence_filter = Persistence(level=persistence)

    @property
    def mature(self) -> bool:
        return self._age >= self.maturity

    def update(self, candle: Candle) -> Advice:
        advice = self.tick(candle)

        if self.mature:
            advice = Advice.combine(
                self._mid_trend_filter.update(advice),
                self._persistence_filter.update(advice),
            )
        else:
            assert advice is Advice.NONE

        self._age = min(self._age + 1, self.maturity)

        self.advice = advice
        return advice

    def tick(self, candle: Candle) -> Advice:
        pass

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
