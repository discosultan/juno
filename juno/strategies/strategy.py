from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict

from juno import Advice, Candle, Trend


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
        from_index = 0
        for names, constraint in type(self).meta().items():
            # Normalize scalars into a single element tuples.
            if not isinstance(names, tuple):
                names = names,

            to_index = from_index + len(names)
            inputs = args[from_index:to_index]

            if not constraint.validate(*inputs):
                raise ValueError(
                    f'Incorrect argument(s): {",".join(map(str, inputs))} for '
                    f'parameter(s): {",".join(names)}'
                )

            from_index = to_index

    @staticmethod
    def advice(trend: Trend, changed: bool) -> Advice:
        return {
            Trend.UP: Advice.BUY,
            Trend.DOWN: Advice.SELL,
        }.get(trend, Advice.NONE) if changed else Advice.NONE
