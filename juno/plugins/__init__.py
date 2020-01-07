import importlib
from types import ModuleType
from typing import Any, AsyncContextManager, Dict, List, cast

from juno.agents import Agent


class PluginModuleType(ModuleType):
    @staticmethod
    def activate(agent: Agent, config: Dict[str, Any]) -> AsyncContextManager[None]:
        pass


# Only supports loading a type of plugin once (not the same plugin with different configs).
def list_plugins(agent_config_map: Dict[Agent, Dict[str, Any]],
                 config: Dict[str, Any]) -> List[AsyncContextManager[None]]:
    agent_plugin_names = {a: c.get('plugins', []) for a, c in agent_config_map.items()}

    plugins = []
    for agent, plugin_names in agent_plugin_names.items():
        for name in plugin_names:
            plugin_module = importlib.import_module(f'juno.plugins.{name}')
            if not plugin_module:
                raise ValueError(f'Plugin {name} not found')
            plugin_module = cast(PluginModuleType, plugin_module)
            activation_fn = plugin_module.activate
            if not activation_fn:
                raise ValueError(f'Plugin {name} is missing "activate" function')
            plugins.append(activation_fn(agent, config.get(name, {})))
    return plugins
