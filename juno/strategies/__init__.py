import inspect
import sys
from typing import Any, Dict, Type

from .mamacx import MAMACX
from .strategy import Meta, Strategy

__all__ = [
    'MAMACX',
    'Meta',
    'Strategy',
    'new_strategy',
    'get_strategy_type',
]

_strategies: Dict[str, Type[Strategy]] = {
    name.lower(): obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
}


def new_strategy(config: Dict[str, Any]) -> Strategy:
    type_ = config['type']
    strategy_cls = _strategies.get(type_)
    if strategy_cls is None:
        raise ValueError(f'Strategy {type_} not found')
    return strategy_cls(**{k: v for k, v in config.items() if k != 'type'})  # type: ignore


def get_strategy_type(name: str) -> Type[Strategy]:
    return _strategies[name]
