import asyncio
from collections import defaultdict
import logging


_log = logging.getLogger(__name__)


class Wallet:

    def __init__(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._exchange_balances = defaultdict(dict)
        self._initial_balances_fetched = asyncio.Event()

    async def __aenter__(self):
        self._sync_balances_task = asyncio.get_running_loop().create_task(
            self._sync_all_balances())
        await self._initial_balances_fetched.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sync_balances_task.cancel()

    def get_balance(self, exchange, asset):
        return self._exchange_balances[exchange][asset]

    async def _sync_all_balances(self):
        try:
            await asyncio.gather(*(self._sync_balances(e) for e in self._exchanges.keys()))
        except asyncio.CancelledError:
            _log.info('balance sync task cancelled')

    async def _sync_balances(self, exchange):
        async for balances in self._exchanges[exchange].stream_balances():
            self._exchange_balances[exchange] = balances
            if not self._initial_balances_fetched.is_set():
                self._initial_balances_fetched.set()
