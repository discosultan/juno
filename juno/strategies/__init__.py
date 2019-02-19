import inspect
import sys
from typing import Any, Dict

from .ema_ema_cx import EmaEmaCX  # noqa


_strategies = {name.lower(): obj for name, obj
               in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def new_strategy(config: Dict[str, Any]) -> Any:
    name = config.pop('name')
    strategy_cls = _strategies.get(name)
    if strategy_cls is None:
        raise ValueError(f'strategy {name} not found')
    return strategy_cls(**config)
