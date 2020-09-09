from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Dict, List, Optional, Set, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Balance, ExchangeException
from juno.asyncio import Event, cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    class BalanceSyncContext:
        def __init__(self) -> None:
            self.balances: Dict[str, Balance] = {}
            self.updated: Event[None] = Event(autoclear=True)

        def clear(self) -> None:
            self.updated.clear()

    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._open_accounts: Dict[str, Set[str]] = {}

        # Balance sync state.
        # Key: (exchange, account)
        self._balance_sync_tasks: Dict[Tuple[str, str], asyncio.Task] = {}
        self._balance_sync_ctxs: Dict[Tuple[str, str], Wallet.BalanceSyncContext] = defaultdict(
            Wallet.BalanceSyncContext
        )
        self._balance_sync_counters: Dict[Tuple[str, str], int] = defaultdict(int)

    async def __aenter__(self) -> Wallet:
        await asyncio.gather(
            *(self._fetch_open_accounts(e) for e in self._exchanges.keys())
        )
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._balance_sync_tasks.values())

    @asynccontextmanager
    async def sync_balances(
        self, exchange: str, account: str
    ) -> AsyncIterator[BalanceSyncContext]:
        key = (exchange, account)
        ctx = self._balance_sync_ctxs[key]

        if self._balance_sync_counters[key] == 0:
            self._balance_sync_counters[key] += 1
            synced = asyncio.Event()
            self._balance_sync_tasks[key] = create_task_cancel_on_exc(
                self._sync_balances(exchange, account, synced)
            )
            await synced.wait()
        else:
            self._balance_sync_counters[key] += 1

        try:
            yield ctx
        finally:
            self._balance_sync_counters[key] -= 1
            if self._balance_sync_counters[key] == 0:
                ctx.clear()
                await cancel(self._balance_sync_tasks[key])

    async def get_balance(
        self,
        exchange: str,
        account: str,
        asset: str,
    ) -> Balance:
        if account == 'isolated':
            raise ValueError('Ambiguous account: isolated')
        # Currently, for Binance, we need to put all isolated margin accounts into an umbrella
        # 'isolated' account when requesting balances.
        account_arg = account if account in ['spot', 'margin'] else 'isolated'
        return (await self._exchanges[exchange].map_balances(account=account_arg))[account][asset]

    async def map_balances(
        self,
        exchange: str,
        accounts: List[str],
        significant: Optional[bool] = None,
    ) -> Dict[str, Dict[str, Balance]]:
        account_args = {a if a in ['spot', 'margin'] else 'isolated' for a in accounts}

        exchange_instance = self._exchanges[exchange]
        result: Dict[str, Dict[str, Balance]] = {}
        balances = await asyncio.gather(
            *(exchange_instance.map_balances(account=a) for a in account_args)
        )
        for balance in balances:
            result.update(balance)
        if 'isolated' not in accounts:
            for key in list(result.keys()):
                if key not in accounts:
                    del result[key]
        # Filtering.
        if significant is not None:
            result = {
                k: {
                    a: b for a, b in v.items() if b.significant == significant
                } for k, v in result.items()
            }
        return result

    async def transfer(
        self, exchange: str, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        await self._ensure_account(exchange, to_account)
        await self._exchanges[exchange].transfer(
            asset=asset, size=size, from_account=from_account, to_account=to_account
        )

    async def borrow(self, exchange: str, asset: str, size: Decimal, account: str) -> None:
        await self._ensure_account(exchange, account)
        await self._exchanges[exchange].borrow(asset=asset, size=size, account=account)

    async def repay(self, exchange: str, asset: str, size: Decimal, account: str) -> None:
        await self._ensure_account(exchange, account)
        await self._exchanges[exchange].repay(asset=asset, size=size, account=account)

    async def get_max_borrowable(self, exchange: str, asset: str, account: str) -> Decimal:
        await self._ensure_account(exchange, account)
        return await self._exchanges[exchange].get_max_borrowable(asset=asset, account=account)

    async def _ensure_account(self, exchange: str, account: str) -> None:
        if account in self._open_accounts[exchange]:
            return
        try:
            await self._exchanges[exchange].create_account(account)
            self._open_accounts[exchange].add(account)
        except ExchangeException:
            _log.info(f'account {account} already created')

    async def _fetch_open_accounts(self, exchange: str) -> None:
        open_accounts = await self._exchanges[exchange].list_open_accounts()
        self._open_accounts[exchange] = set(open_accounts)

    async def _sync_balances(self, exchange: str, account: str, synced: asyncio.Event) -> None:
        ctx = self._balance_sync_ctxs[(exchange, account)]
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                async for balances in self._stream_balances(exchange, account):
                    _log.info(f'received {exchange} {account} balance update')
                    # TODO: Use Python 3.9 dict |= operator.
                    ctx.balances = {**ctx.balances, **balances}
                    if is_first:
                        is_first = False
                        synced.set()
                    ctx.updated.set()

    async def _stream_balances(
        self, exchange: str, account: str
    ) -> AsyncIterable[Dict[str, Balance]]:
        exchange_instance = self._exchanges[exchange]

        if exchange_instance.can_stream_balances:
            # TODO: We are not receiving `interest` nor `borrowed` data through web socket updates.
            # Figure out a better way to handle these. Perhaps separate balance and borrow state.
            async with exchange_instance.connect_stream_balances(account=account) as stream:
                # Get initial status from REST API.
                yield (await self.map_balances(exchange=exchange, accounts=[account]))[account]

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(
                f'{exchange} does not support streaming {account} balances; fething only initial '
                'balances; further updates not implemented'
            )
            yield (await exchange_instance.map_balances(account))[account]
