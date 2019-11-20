from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterable, Dict, List

import backoff

from juno import Balance
from juno.asyncio import Barrier, cancel, cancelable
from juno.exchanges import Exchange
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._exchange_balances: Dict[str, Dict[str, Balance]] = defaultdict(dict)

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = Barrier(len(self._exchanges))
        self._sync_all_balances_task = asyncio.create_task(cancelable(self._sync_all_balances()))
        await self._initial_balances_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_all_balances_task)

    def get_balance(self, exchange: str, asset: str) -> Balance:
        balance = self._exchange_balances[exchange][asset]
        return balance

    async def _sync_all_balances(self) -> None:
        await asyncio.gather(*(self._sync_balances(e) for e in self._exchanges.keys()))

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def _sync_balances(self, exchange: str) -> None:
        is_first = True
        async for balances in self._stream_balances(exchange):
            _log.info(f'received balance update from {exchange}')
            self._exchange_balances[exchange] = balances
            if is_first:
                is_first = False
                self._initial_balances_fetched.release()

    async def _stream_balances(self, exchange: str) -> AsyncIterable[Dict[str, Balance]]:
        exchange_instance = self._exchanges[exchange]

        async with exchange_instance.connect_stream_balances() as stream:
            # Get initial status from REST API.
            yield await exchange_instance.get_balances()

            # Stream future updates over WS.
            async for balances in stream:
                yield balances
