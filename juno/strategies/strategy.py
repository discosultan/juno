from typing import Any, Dict, Generic, Optional, Tuple, TypeVar, Union

from juno import Advice, Candle
from juno.math import Constraint

T = TypeVar('T')


class Persistence(Generic[T]):
    _age: int = 0
    _level: int
    _allow_next: bool
    _value: Optional[T] = None
    _potential: Optional[T] = None
    _changed: bool = False

    """The number of ticks required to confirm a value."""
    def __init__(self, level: int, allow_initial: bool = False) -> None:
        self._level = level
        self._allow_next = allow_initial

    @property
    def persisted(self) -> bool:
        return self._value is not None and self._age >= self._level

    def update(self, value: Optional[T]) -> Tuple[bool, bool]:
        if (
            value is None
            or (self._potential is not None and value is not self._potential)
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
    req_history: int

    _maturity: int
    _persistence: Persistence[Advice]
    _advice: Optional[Advice] = None
    _age: int = 0

    @staticmethod
    def meta() -> Meta:
        pass

    def __init__(self, maturity: int = 0, persistence: int = 0) -> None:
        self.req_history = maturity

        self._maturity = maturity
        self._persistence = Persistence(persistence)

    @property
    def advice(self) -> Optional[Advice]:
        advice = None
        if self._persistence.persisted:
            advice = self._advice
        return advice

    @property
    def mature(self) -> bool:
        return self._age >= self._maturity

    def update(self, candle: Candle) -> None:
        self._advice = self.tick(candle)
        self._persistence.update(self._advice)
        self._age = min(self._age + 1, self._maturity)

    def tick(self, candle: Candle) -> Optional[Advice]:
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
