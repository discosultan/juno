import inspect
import os
import sys
from typing import Any, Dict

from .binance import Binance  # noqa
from .coinbase import Coinbase  # noqa


def map_exchanges() -> Dict[str, Any]:
    services = {}
    for name, type_ in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        keys = type_.__init__.__annotations__.keys()  # type: ignore
        keys = (k for k in keys if k != 'return')
        kwargs = {key: os.getenv(f'JUNO_{name.upper()}_{key.upper()}') for key in keys}
        if all(kwargs.values()):
            services[name.lower()] = type_(**kwargs)  # type: ignore
    return services
