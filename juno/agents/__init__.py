import inspect
import itertools
import sys
from typing import Any, Dict, List, Set, Tuple

from .agent import Agent
from .backtest import Backtest  # noqa

_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)
           # if callable(getattr(type_, 'run', None))
           }


def list_agents(components: Dict[str, Any], config: Dict[str, Any]
                ) -> List[Tuple[Agent, Dict[str, Any]]]:
    agents = []
    for agent_config in config['agents']:
        name = agent_config['name']
        agent_type = _agents.get(name)
        if not agent_type:
            raise ValueError(f'Agent {name} not found')
        agents.append((agent_type(components), agent_config))
    return agents


# def run_agent(components: Dict[str, Any], config: Dict[str, Any]) -> Any:
#     name = config['name']
#     agent_type = _agents.get(name)
#     if not agent_type:
#         raise ValueError(f'Agent {name} not found')
#     return agent_type(components).run(**{k: v for k, v in config.items() if k != 'name'})


def list_required_component_names(config: Dict[str, Any]) -> Set[str]:
    agent_names = (a['name'] for a in config['agents'])
    return set(itertools.chain.from_iterable(
        (type_.required_components for name, type_ in _agents.items() if name in agent_names)))
