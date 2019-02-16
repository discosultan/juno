import inspect
import sys
from typing import Any, Dict, Optional, Set

from .memory import Memory  # noqa
from .sqlite import SQLite  # noqa
from juno.utils import recursive_iter


_storages = {name.lower(): obj for name, obj
             in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def map_storages(config: Dict[str, Any], names: Optional[Set[str]] = None) -> Dict[str, Any]:
    services = {}
    for name, type_ in _storages.items():
        if names is None or name in names:
            services[name] = type_()
    return services


def list_required_storage_names(config: Dict[str, Any]) -> Set[str]:
    result = set()
    for keys, v in recursive_iter(config):
        if keys[-1] == 'storage':
            result.add(v)
        elif keys[-1] == 'storages':
            result.update(v)
    return result
