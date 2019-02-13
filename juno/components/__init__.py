import inspect
import sys
from typing import Any, Dict, Set

from .informant import Informant  # noqa
from .orderbook import Orderbook  # noqa
from .wallet import Wallet  # noqa


_components = {name.lower(): obj for name, obj
               in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def map_components(names: Set[str], services: Dict[str, Any], config: Dict[str, Any]
                   ) -> Dict[str, Any]:
    components = {}
    for name, type_ in _components.items():
        if name in names:
            components[name] = type_(services=services, config=config)
    return components
