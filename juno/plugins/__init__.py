import importlib
from typing import Any, AsyncContextManager, Dict, List

from juno.agents import Agent


# TODO: only supports loading a type of plugin once (not the same plugin with different configs)
def list_plugins(agents: List[Agent], config: Dict[str, Any]
                 ) -> List[AsyncContextManager[None]]:
    agent_plugin_names = {a: a.config.get('plugins', []) for a in agents}

    plugins = []
    for agent, plugin_names in agent_plugin_names.items():
        for name in plugin_names:
            plugin_module = importlib.import_module(f'juno.plugins.{name}')
            if not plugin_module:
                raise ValueError(f'Plugin {name} not found')
            activation_fn = getattr(plugin_module, 'activate')
            if not activation_fn:
                raise ValueError(f'Plugin {name} is missing "activate" function')
            plugins.append(activation_fn(agent, config[name]))
    return plugins
