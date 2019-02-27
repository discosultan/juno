import inspect
import sys
from typing import Any, Dict, Optional, Set, get_type_hints

from .binance import Binance  # noqa
from .coinbase import Coinbase  # noqa
from .exchange import Exchange  # noqa

_exchanges = {name.lower(): obj for name, obj in inspect.getmembers(
    sys.modules[__name__], lambda m: inspect.isclass(m) and m is not Exchange)}


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
