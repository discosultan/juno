from typing import Any, Dict, Optional, Tuple, Union

from juno import Advice, Candle
from juno.math import Constraint


class IgnoreNotMatureAndMidTrend:
    """Ignore advice if not mature and first matured advice if middle of trend."""
    _maturity: int
    _ignore_mid_trend: bool
    _previous: Optional[Advice] = None
    _age: int = 0

    def __init__(self, maturity: int, ignore_mid_trend: bool) -> None:
        self._maturity = maturity
        self._ignore_mid_trend = ignore_mid_trend

    def update(self, value: Advice) -> Advice:
        result = Advice.NONE
        if self._age >= self._maturity:
            if self._ignore_mid_trend:
                if self._previous is None:
                    self._previous = value
                elif value is not self._previous:
                    self._enabled = False
                    result = value
            else:
                result = value

        self._previous = value
        self._age = min(self._age + 1, self._maturity)
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

    _ignore_not_mature_and_mid_trend: IgnoreNotMatureAndMidTrend
    _persistence: Persistence
    _changed: Changed
    _age: int = 0

    @staticmethod
    def meta() -> Meta:
        return Meta()

    def __init__(
        self, maturity: int = 0, persistence: int = 0, ignore_first: bool = False
    ) -> None:
        self.maturity = maturity
        self._ignore_not_mature_and_mid_trend = IgnoreNotMatureAndMidTrend(
            maturity=maturity, ignore_mid_trend=ignore_first
        )
        self._persistence = Persistence(level=persistence)
        self._changed = Changed(enabled=True)

    @property
    def mature(self) -> bool:
        return self._age >= self.maturity

    def update(self, candle: Candle) -> Advice:
        advice = self.tick(candle)
        advice = self._ignore_not_mature_and_mid_trend.update(advice)
        advice = self._persistence.update(advice)
        advice = self._changed.update(advice)
        self.advice = advice

        self._age = min(self._age + 1, self.maturity)

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
