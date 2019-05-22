import inspect
import sys
from typing import Any, Dict, Set, Type

from juno.utils import ischild

from .agent import Agent
from .backtest import Backtest  # noqa
from .live import Live  # noqa
from .paper import Paper  # noqa

# TODO: Move summary module out of the package.
_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)
           if ischild(type_, Agent)}


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
