import inspect
import sys
from typing import Any, Dict, cast

from .emaemacx import EmaEmaCX  # noqa
from .strategy import Strategy

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


def get_strategy_type(name: str) -> Strategy:
    return _strategies[name]
