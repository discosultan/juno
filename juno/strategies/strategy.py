from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, Tuple, Union

from juno import Advice, Candle, Trend
from juno.math import Constraint


class Meta:
    def __init__(
        self,
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
    ) -> None:
        self.constraints = constraints


class Strategy(ABC):
    meta: Meta

    @abstractproperty
    def req_history(self) -> int:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> Advice:
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

    @staticmethod
    def advice(trend: Trend, changed: bool) -> Advice:
        return {
            Trend.UP: Advice.BUY,
            Trend.DOWN: Advice.SELL,
        }.get(trend, Advice.NONE) if changed else Advice.NONE
