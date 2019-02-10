import sys
from typing import Any

from .backtest import backtest  # noqa


_agents = {name.lower(): obj for name, obj in sys.modules[__name__].__dict__.items()
           if callable(obj)}


def new_agent(components: dict, config: dict) -> Any:
    name = config.pop('name')
    agent = _agents.get(name)
    if not agent:
        raise ValueError(f'agent {name} not found')
    return agent(components, **config)
