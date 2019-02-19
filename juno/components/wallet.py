from __future__ import annotations
import asyncio
from collections import defaultdict
import logging
from typing import Any, Dict

from juno import Balance
from juno.exchanges import Exchange


_log = logging.getLogger(__name__)


class Wallet:

    def __init__(self, services: Dict[str, Any], config: Dict[str, Any]) -> None:
        self._exchanges: Dict[str, Exchange] = {
            k: v for k, v in services.items() if isinstance(v, Exchange)}
        self._exchange_balances: Dict[str, Dict[str, Balance]] = defaultdict(dict)

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = asyncio.Event()
        self._sync_all_balances_task = asyncio.create_task(self._sync_all_balances())
        await self._initial_balances_fetched.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sync_all_balances_task.cancel()
        await self._sync_all_balances_task

    def get_balance(self, exchange: str, asset: str) -> Balance:
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
