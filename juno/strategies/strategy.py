from typing import Any, Dict, Tuple, Union

from juno import Advice, Candle
from juno.math import Constraint


class Persistence:
    """The number of ticks required to confirm an advice."""
    _age: int = 0
    _level: int
    _allow_next: bool
    _value: Advice = Advice.NONE
    _potential: Advice = Advice.NONE
    _changed: bool = False

    def __init__(self, level: int, allow_initial: bool = False) -> None:
        self._level = level
        self._allow_next = allow_initial

    @property
    def persisted(self) -> bool:
        return self._value is not Advice.NONE and self._age >= self._level

    def update(self, value: Advice) -> Tuple[bool, bool]:
        if (
            value is Advice.NONE
            or (self._potential is not Advice.NONE and value is not self._potential)
        ):
            self._allow_next = True

        if value is not self._potential:
            self._age = 0
            self._potential = value

        if (
            self._allow_next
            and self._age == self._level
            and self._potential is not self._value
        ):
            self._value = self._potential
            self._changed = True
        else:
            self._changed = False

        self._age = min(self._age + 1, self._level)

        return self.persisted, self._changed


class Meta:
    def __init__(
        self,
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
    ) -> None:
        self.constraints = constraints


class Strategy:
    maturity: int
    _persistence: Persistence
    advice: Advice = Advice.NONE
    _age: int = 0

    @staticmethod
    def meta() -> Meta:
        return Meta()

    def __init__(
        self, maturity: int = 0, persistence: int = 0, allow_initial: bool = False
    ) -> None:
        self.maturity = maturity
        self._persistence = Persistence(level=persistence, allow_initial=allow_initial)

    @property
    def mature(self) -> bool:
        return self._age >= self.maturity

    def update(self, candle: Candle) -> Advice:
        advice = self.tick(candle)
        persisted, _changed = self._persistence.update(advice)
        self._age = min(self._age + 1, self.maturity)
        # TODO: walrus
        self.advice = advice if persisted else Advice.NONE
        return self.advice

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
