import inspect
import itertools
import sys
from typing import Any, Dict, Set

from .backtest import Backtest  # noqa


_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def run_agent(components: Dict[str, Any], config: Dict[str, Any]) -> Any:
    name = config.pop('name')
    agent_type = _agents.get(name)
    if not agent_type:
        raise ValueError(f'agent {name} not found')
    return agent_type(components).run(**config)


def list_required_component_names(config: Dict[str, Any]) -> Set[str]:
    agent_names = (a['name'] for a in config['agents'])
    return set(itertools.chain.from_iterable(
        (type_.required_components for name, type_ in _agents.items() if name in agent_names)))
