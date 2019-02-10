import asyncio
from collections import defaultdict
from decimal import Decimal
import logging


_log = logging.getLogger(__name__)


class Wallet:

    def __init__(self, services: dict, config: dict) -> None:
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._exchange_balances = defaultdict(dict)

    async def __aenter__(self):
        self._initial_balances_fetched = asyncio.Event()
        self._sync_all_balances_task = asyncio.create_task(self._sync_all_balances())
        await self._initial_balances_fetched.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sync_all_balances_task.cancel()
        await self._sync_all_balances_task

    def get_balance(self, exchange: str, asset: str) -> Decimal:
        return self._exchange_balances[exchange][asset]

    async def _sync_all_balances(self) -> None:
        try:
            await asyncio.gather(*(self._sync_balances(e) for e in self._exchanges.keys()))
        except asyncio.CancelledError:
            _log.info('balance sync task cancelled')

    async def _sync_balances(self, exchange: str) -> None:
        async for balances in self._exchanges[exchange].stream_balances():
            self._exchange_balances[exchange] = balances
            if not self._initial_balances_fetched.is_set():
                self._initial_balances_fetched.set()
