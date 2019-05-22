import inspect
import sys
from typing import Any, Dict, Set, Type

from .agent import Agent
from .backtest import Backtest  # noqa
from .live import Live  # noqa
from .paper import Paper  # noqa

# TODO: Move summary classes out of the module.
_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)
           if Agent in inspect.getmro(type_)[1:]}  # Derives from Agent.


def map_agent_types(config: Dict[str, Any]) -> Dict[str, Type[Agent]]:
    result = {}
    mapped: Set[str] = set()
    for agent_config in config['agents']:
        name = agent_config['name']
        if name in mapped:
            continue
        agent_type = _agents.get(name)
        if not agent_type:
            raise ValueError(f'Agent {name} not found')
        result[name] = agent_type
        mapped.add(name)
    return result
