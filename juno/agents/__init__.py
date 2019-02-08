from typing import Any

from .backtest import  # noqa


_agents = {name.lower(): obj for name, obj in sys.modules[__name__].__dict__.items()
           if callable(obj)}

def new_agent(name: str) -> Any:
    agent = _agents.get(name)
    if not agent:
        raise ValueError(f'agent {name} not found')
    return agent
