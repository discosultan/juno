import asyncio
from collections import defaultdict
import logging


_log = logging.getLogger(__package__)


class Wallet:

    def __init__(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._exchange_balances = defaultdict(dict)

    async def __aenter__(self):
        await self._sync_all_balances()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def get_balance(self, exchange, asset):
        return self._exchange_balances[exchange][asset]

    async def _sync_all_balances(self):
        return await asyncio.gather(*(self._sync_balances(e) for e in self._exchanges.keys()))

    async def _sync_balances(self, exchange):
        balances = await self._exchanges[exchange].map_balances()
        self._exchange_balances[exchange] = balances
