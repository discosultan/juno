from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict

from juno import Advice, Candle


class Strategy(ABC):
    @abstractproperty
    def req_history(self) -> int:
        pass

    @staticmethod
    @abstractmethod
    def meta() -> Dict[Any, Any]:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> Advice:
        pass

    def validate(self, *args: Any) -> None:
        # Assumes ordered.
        arg_index = 0
        for names, constraint in type(self).meta():
            # Normalize scalars into a single element tuples.
            if names is not tuple:
                names = names,

            arg_count = len(names)

            if not constraint.validate(args[arg_index:arg_count]):
                raise ValueError(f'Incorrect argument(s) for parameter(s): {",".join(names)}')

            arg_index += arg_count
