import inspect
import sys
from typing import Any, Dict, get_type_hints, Optional, Set

from .binance import Binance  # noqa
from .coinbase import Coinbase  # noqa
from juno.utils import recursive_iter


_exchanges = {name.lower(): obj for name, obj
              in inspect.getmembers(sys.modules[__name__], inspect.isclass)}


def map_exchanges(config: Dict[str, Any], names: Optional[Set[str]] = None) -> Dict[str, Any]:
    services = {}
    for name, type_ in _exchanges.items():
        if names is None or name in names:
            exchange_config = config[name]
            keys = get_type_hints(type_.__init__).keys()  # type: ignore
            param_keys = (k for k in keys if k != 'return')
            kwargs = {key: exchange_config.get(key) for key in param_keys}
            if not all(kwargs.values()):
                raise ValueError(f'Exchange {name} not properly configured: {kwargs}')
            services[name] = type_(**kwargs)
    return services


def list_required_exchange_names(config: Dict[str, Any]) -> Set[str]:
    result = set()
    for keys, v in recursive_iter(config):
        if keys[-1] == 'exchange':
            result.add(v)
        elif keys[-1] == 'exchanges':
            result.update(v)
    return result
