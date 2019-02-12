import inspect
import sys
from typing import Any, Dict

from .memory import Memory  # noqa
from .sqlite import SQLite  # noqa


def map_storages() -> Dict[str, Any]:
    services = {}
    for name, type_ in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        services[name.lower()] = type_()
    return services
