import inspect
import itertools
import sys
from typing import Any, Dict, List, Set

from .agent import Agent
from .backtest import Backtest  # noqa
from .live import Live  # noqa
from .paper import Paper  # noqa

_agents = {name.lower(): type_ for name, type_
           in inspect.getmembers(sys.modules[__name__], inspect.isclass)
           if Agent in inspect.getmro(type_)[1:]}  # Derives from Agent.


def list_agents(components: Dict[str, Any], config: Dict[str, Any]
                ) -> List[Agent]:
    agents = []
    for agent_config in config['agents']:
        name = agent_config['name']
        agent_type = _agents.get(name)
        if not agent_type:
            raise ValueError(f'Agent {name} not found')
        agents.append(agent_type(components, agent_config))
    return agents


def list_required_component_names(config: Dict[str, Any],
                                  agents: Dict[str, Agent] = _agents) -> Set[str]:
    agent_names = set((a['name'] for a in config['agents']))
    return set(itertools.chain.from_iterable(
        (type_.required_components for name, type_ in agents.items() if name in agent_names)))
