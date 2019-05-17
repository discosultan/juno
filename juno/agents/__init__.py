import inspect
import itertools
import sys
from collections import defaultdict
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Dict, Iterable, List, Optional, Set, Type, get_type_hints

from juno import components, exchanges, storages

from .agent import Agent
from .backtest import Backtest  # noqa
from .live import Live  # noqa
from .paper import Paper  # noqa

# TODO: Move summary classes out of the module.
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


# TODO: Move summary classes out of the module.
_agent_types_map = {name.lower(): type_ for name, type_
                    in inspect.getmembers(sys.modules[__name__], inspect.isclass)
                    if Agent in inspect.getmro(type_)[1:]}  # Derives from Agent.

# def _isconcreteclass(obj: Any) -> bool:
#     return inspect.isclass(obj) and not inspect.isabstract(obj)

# _component_modules = (components, exchanges, storages)
# _components = set((type_ for module in _component_modules
#                    for _name, type_ in inspect.getmembers(module, _isconcreteclass)))


# def _map_dependencies(types: Iterable[type], graph: Optional[Dict[type, List[type]]] = None
#                       ) -> Dict[type, List[type]]:
#     if not graph:
#         graph = defaultdict(list)

#     for type_ in types:
#         if type_ in graph:
#             continue

#         deps = [t for t in get_type_hints(type_).values() if t in _components]
#         graph[type_] = deps
#         graph = _map_dependencies(deps, graph)

#     return graph


# _dependency_graph = _map_dependencies(_agent_types_map.values())


# @asynccontextmanager
# async def initialize_agents(config: Dict[str, Any]) -> List[Agent]:
#     async with AsyncExitStack() as stack:
#         agents = []
#         initialized_dependencies: Dict[type, Any] = {}
#         for agent_config in config['agents']:
#             name = agent_config['name']
#             agent_type = _agent_types_map.get(name)
#             if not agent_type:
#                 raise ValueError(f'Agent {name} not found')
#             deps = _dependency_graph[agent_type]
#             # result.add(agent_type)
#             _dependency_graph
#         yield agents
