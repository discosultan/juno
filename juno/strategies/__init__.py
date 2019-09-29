import inspect
import sys
from typing import Any, Dict, Type, cast

from .mamacx import MAMACX
from .strategy import Meta, Strategy

__all__ = [
    'MAMACX',
    'Meta',
    'Strategy',
    'new_strategy',
    'get_strategy_type',
]

_strategies = {
    name.lower(): obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
}


# TODO: use a more generalized approach
def new_strategy(config: Dict[str, Any]) -> Strategy:
    type_ = config['type']
    strategy_cls = _strategies.get(type_)
    if strategy_cls is None:
        raise ValueError(f'Strategy {type_} not found')
    return cast(Strategy, strategy_cls(**{k: v for k, v in config.items() if k != 'type'}))


def get_strategy_type(name: str) -> Type[Strategy]:
    return _strategies[name]
