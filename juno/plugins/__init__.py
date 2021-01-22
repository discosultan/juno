import importlib
import inspect
from typing import Iterable, Type

from .plugin import Plugin


def map_plugin_types(names: Iterable[str]) -> dict[str, Type[Plugin]]:
    plugins = {}
    for name in names:
        plugin_module = importlib.import_module(f'juno.plugins.{name}')
        if not plugin_module:
            raise ValueError(f'Module for plugin {name} not found')
        members = inspect.getmembers(
            plugin_module,
            lambda o: inspect.isclass(o) and issubclass(o, Plugin) and o is not Plugin,
        )
        if len(members) != 1:
            raise ValueError(
                f'Found more than one plugin {name} in {plugin_module.__name__}: {members}'
            )
        plugins[name] = members[0][1]
    return plugins


__all__ = [
    'Plugin',
    'map_plugin_types',
]
