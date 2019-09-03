from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, NamedTuple, Tuple

from juno import Advice, Candle, Trend
from juno.math import Randomizer
from juno.utils import get_args_by_param_names


class Meta(NamedTuple):
    args: Dict[str, Randomizer]
    constraints: Dict[Tuple[str, ...], Any]
    identifier: str


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
        for i, (name, randomizer) in enumerate(meta.args.items()):
            if not randomizer.validate(args[i]):
                raise ValueError(f'Incorrect argument: {args[i]} for parameter: {name}')
        for names, constraint in meta.constraints.items():
            if not constraint(*get_args_by_param_names(args, meta.args.keys(), names)):
                raise ValueError(f'Constraint not satisfied: {names} {constraint}')

    @staticmethod
    def advice(trend: Trend, changed: bool) -> Advice:
        return {
            Trend.UP: Advice.BUY,
            Trend.DOWN: Advice.SELL,
        }.get(trend, Advice.NONE) if changed else Advice.NONE
