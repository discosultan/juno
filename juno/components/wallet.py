from collections import defaultdict
import logging


_log = logging.getLogger(__package__)


class Wallet:

    def __init____(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._exchange_balances = defaultdict(dict)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass
