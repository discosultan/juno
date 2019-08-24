import inspect
import sys
from typing import Any, Dict, Type, cast

from .mamacx import MAMACX
from .strategy import Strategy

__all__ = [
    'MAMACX',
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
    name = config['name']
    strategy_cls = _strategies.get(name)
    if strategy_cls is None:
        raise ValueError(f'Strategy {name} not found')
    return cast(Strategy, strategy_cls(**{k: v for k, v in config.items() if k != 'name'}))


def get_strategy_type(name: str) -> Type[Strategy]:
    return _strategies[name]
