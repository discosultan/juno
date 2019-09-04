import re
from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, Optional, Tuple

from juno import Advice, Candle, Trend
from juno.math import Randomizer
from juno.utils import get_args_by_params


class Meta:
    def __init__(
        self, params: Dict[str, Randomizer] = {}, constraints: Dict[Tuple[str, ...], Any] = {},
        identifier: Optional[str] = None
    ) -> None:
        self.params = params
        self.constraints = constraints
        self.identifier = identifier
        self.identifier_params = re.findall(r'\{(.*?)\}', identifier) if identifier else []
        if not all((p in params.keys() for p in self.identifier_params)):
            raise ValueError('Param from identifier missing in params.')
        self.non_identifier_params = [k for k in params.keys() if k not in self.identifier_params]


class Strategy(ABC):
    @abstractproperty
    def req_history(self) -> int:
        pass

    @staticmethod
    @abstractmethod
    def meta() -> Meta:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> Advice:
        pass

    def validate(self, *args: Any) -> None:
        # Assumes ordered.
        meta = type(self).meta()
        for i, (name, randomizer) in enumerate(meta.params.items()):
            if not randomizer.validate(args[i]):
                raise ValueError(f'Incorrect argument: {args[i]} for parameter: {name}')
        for names, constraint in meta.constraints.items():
            if not constraint(*get_args_by_params(meta.params.keys(), args, names)):
                raise ValueError(f'Constraint not satisfied: {names} {constraint} {args}')

    @staticmethod
    def advice(trend: Trend, changed: bool) -> Advice:
        return {
            Trend.UP: Advice.BUY,
            Trend.DOWN: Advice.SELL,
        }.get(trend, Advice.NONE) if changed else Advice.NONE
