import inspect
import sys
from typing import Any, Dict, Optional, Set, Type

from juno.typing import get_input_type_hints

from .binance import Binance  # noqa
from .coinbase import Coinbase  # noqa
from .exchange import Exchange  # noqa

_exchanges = {name.lower(): obj for name, obj in inspect.getmembers(
    sys.modules[__name__], lambda m: inspect.isclass(m) and m is not Exchange)}


def map_exchanges(config: Dict[str, Any], names: Optional[Set[str]] = None) -> Dict[str, Any]:
    services = {}
    for name, type_ in _exchanges.items():
        if names is None or name in names:
            services[name] = create_exchange(type_, config)
    return services


def create_exchange(type_: Type[Exchange], config: Dict[str, Any]) -> Optional[Exchange]:
    name = type_.__name__.lower()
    exchange_config = config.get(name)
    if not exchange_config:
        raise ValueError(f'Missing config for {name}')
    keys = get_input_type_hints(type_.__init__).keys()
    kwargs = {key: exchange_config.get(key) for key in keys}
    if not all(kwargs.values()):
        raise ValueError(f'Misconfiguration of {name}: {exchange_config}')
    return type_(**kwargs)  # type: ignore
