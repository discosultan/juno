from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Union

from juno import Advice, Candle
from juno.math import Constraint


class Meta:
    def __init__(
        self,
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
    ) -> None:
        self.constraints = constraints


class Strategy(ABC):
    meta: Meta

    def __init__(self, maturity: int = 0, persistence: int = 0) -> None:
        self.req_history = maturity

        self._maturity = maturity
        self._persistence = Persistence(persistence)
        self._advice: Optional[Advice] = None
        self._age = 0

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

    @abstractmethod
    def tick(self, candle: Candle) -> Optional[Advice]:
        pass

    def validate(self, *args: Any) -> None:
        # Assumes ordered.
        from_index = 0
        for names, constraint in type(self).meta.constraints.items():
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


class Persistence:
    """The number of ticks required to confirm a value."""
    def __init__(self, level: int, allow_initial: bool = False) -> None:
        self.age = 0
        self.level = level
        self.allow_next = allow_initial
        self.value = None
        self.potential = None
        self.changed = False

    @property
    def persisted(self) -> bool:
        return self.value is not None and self.age >= self.level

    def update(self, value: Optional[Any]) -> Tuple[bool, bool]:
        if (
            value is None
            or (self.potential is not None and value is not self.potential)
        ):
            self.allow_next = True

        if value is not self.potential:
            self.age = 0
            self.potential = value

        if (
            self.allow_next
            and self.age == self.level
            and self.potential is not self.value
        ):
            self.value = self.potential
            self.changed = True
        else:
            self.changed = False

        self.age = min(self.age + 1, self.level)

        return self.persisted, self.changed
