import sys
from typing import Any

from .ema_ema_cx import EmaEmaCX  # noqa


_strategies = {name.lower(): cls for name, cls in sys.modules[__name__].__dict__.items()
            if isinstance(cls, type)}


def new_strategy(name: str, **kwargs: dict) -> Any:
    strategy_cls = _strategies.get(name)
    if strategy_cls is None:
        raise ValueError(f'strategy {name} not found')
    return strategy_cls(**kwargs)
