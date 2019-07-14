from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

from juno import Balance
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._exchange_balances: Dict[str, Dict[str, Balance]] = defaultdict(dict)

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = asyncio.Event()
        self._sync_all_balances_task = asyncio.create_task(cancelable(self._sync_all_balances()))
        await self._initial_balances_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_all_balances_task)

    def get_balance(self, exchange: str, asset: str) -> Balance:
        balance = self._exchange_balances[exchange][asset]
        _log.info(f'Get balance: {balance}')
        return balance

    async def _sync_all_balances(self) -> None:
        await asyncio.gather(*(self._sync_balances(e) for e in self._exchanges.keys()))

    async def _sync_balances(self, exchange: str) -> None:
        async with self._exchanges[exchange].connect_stream_balances() as balances_stream:
            async for balances in balances_stream:
                self._exchange_balances[exchange] = balances
                if not self._initial_balances_fetched.is_set():
                    self._initial_balances_fetched.set()
