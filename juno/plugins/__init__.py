import importlib
from typing import Any, AsyncContextManager, Dict, Iterable, List, Type, cast

from juno.agents import Agent

from .plugin import Plugin



# Only supports loading a type of plugin once (not the same plugin with different configs).
def list_plugin_types(names: Iterable[str]) -> List[Type[Plugin]]:
    agent_plugin_names = {a: c.get('plugins', []) for a, c in agent_config_map.items()}

    plugins = []
    for name in names:
        plugin_module = importlib.import_module(f'juno.plugins.{name}')
        if not plugin_module:
            raise ValueError(f'Plugin {name} not found')
        plugin_module = cast(PluginModuleType, plugin_module)
        activation_fn = plugin_module.activate
        if not activation_fn:
            raise ValueError(f'Plugin {name} is missing "activate" function')
        plugins.append(activation_fn(agent, config.get(name, {})))
    return plugins
