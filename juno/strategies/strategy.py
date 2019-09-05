import operator
import re
from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, List, Optional, Tuple

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
        self._constraint_getters = {
            k: operator.itemgetter(
                *(i for i, n in enumerate(params.keys()) if n in k)
            ) for k in constraints.keys()
        }
        self._identifier = identifier
        self.identifier_params = re.findall(r'\{(.*?)\}', identifier) if identifier else []
        # self.identifier_indices = [
        #     i for i, n in enumerate(params.keys()) if n in self.identifier_params
        # ]
        # self._identifier_getter = operator.itemgetter(
        #     *(i for i, n in enumerate(params.keys()) if n in self.identifier_params)
        # )
        if not all((p in params.keys() for p in self.identifier_params)):
            raise ValueError('Param from identifier missing in params.')
        self.non_identifier_params = [k for k in params.keys() if k not in self.identifier_params]

    @property
    def identifier(self) -> str:
        if self._identifier is None:
            raise NotImplementedError()
        return self._identifier

    def get_constraint_args(
        self, constraint_keys: Tuple[str, ...], args: List[Any]
    ) -> Tuple[Any, ...]:
        return self._constraint_getters[constraint_keys](args)

    def constraints_satisfied(self, args) -> bool:
        for params, constraint in self.constraints.items():
            if not constraint(*self._constraint_getters[params](args)):
                return False
        return True


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
        meta = type(self).meta
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
