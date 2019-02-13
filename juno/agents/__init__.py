import inspect
import itertools
import sys
from typing import Any, Dict, Iterable, Set

from .backtest import Backtest  # noqa


_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def run_agent(components: Dict[str, Any], config: Dict[str, Any]) -> Any:
    name = config.pop('name')
    agent_type = _agents.get(name)
    if not agent_type:
        raise ValueError(f'agent {name} not found')
    return agent_type(components).run(**config)


def map_required_component_names(agent_names: Iterable[str]) -> Set[str]:
    return set(itertools.chain.from_iterable(
        (type_.required_components for name, type_ in _agents.items() if name in agent_names)))
