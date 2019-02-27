import inspect
import sys
from typing import Any, Dict, Optional, Set

from .informant import Informant  # noqa
from .orderbook import Orderbook  # noqa
from .wallet import Wallet  # noqa

_components = {name.lower(): obj for name, obj
               in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def map_components(services: Dict[str, Any], config: Dict[str, Any],
                   names: Optional[Set[str]] = None) -> Dict[str, Any]:
    components = {}
    for name, type_ in _components.items():
        if names is None or name in names:
            components[name] = type_(services=services, config=config)
    return components
