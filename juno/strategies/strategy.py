import re
from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, Optional, Tuple, Union

from juno import Advice, Candle, Trend
from juno.math import Constraint
from juno.utils import flatten


class Meta:
    def __init__(
        self, constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
        identifier: Optional[str] = None
    ) -> None:
        self.constraints = constraints
        self._identifier = identifier
        self.all_params = list(flatten(self.constraints.keys()))
        self.identifier_params = re.findall(r'\{(.*?)\}', identifier) if identifier else []
        if not all((p in self.all_params for p in self.identifier_params)):
            raise ValueError('Param from identifier missing in params.')
        self.non_identifier_params = [
            k for k in self.all_params if k not in self.identifier_params
        ]

    @property
    def identifier(self) -> str:
        if self._identifier is None:
            raise NotImplementedError()
        return self._identifier


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
