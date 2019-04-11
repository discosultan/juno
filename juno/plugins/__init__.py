import importlib
from typing import Any, AsyncContextManager, Callable, Dict, List

from juno.agents import Agent


# TODO: only supports loading a type of plugin once (not the same plugin with different configs)
def list_plugins(config: Dict[str, Any]) -> List[Callable[[Agent], AsyncContextManager[None]]]:
    plugins = []
    for plugin_config in config['plugins']:
        name = plugin_config['name']
        plugin_module = importlib.import_module(name)
        if not plugin_module:
            raise ValueError(f'Plugin {name} not found')
        activation_fn = getattr(plugin_module, 'activate')
        if not activation_fn:
            raise ValueError(f'Plugin {name} is missing "activate" function')
        plugins.append(lambda agent: activation_fn(agent, plugin_config))
    return plugins
