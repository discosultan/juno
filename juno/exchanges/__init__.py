import inspect
import sys
from typing import Any, Dict

from .binance import Binance  # noqa
from .coinbase import Coinbase  # noqa


def map_exchanges(config: Dict[str, Any]) -> Dict[str, Any]:
    services = {}
    for name, type_ in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        name = name.lower()
        exchange_config = config[name]
        keys = type_.__init__.__annotations__.keys()
        keys = (k for k in keys if k != 'return')
        kwargs = {key: exchange_config.get(key) for key in keys}
        if all(kwargs.values()):
            services[name] = type_(**kwargs)
    return services
