from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import AsyncIterable, Dict, Iterable, List, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Balance, ExchangeException
from juno.asyncio import Event, SlotBarrier, cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


# TODO: Store the state of opened account locally, so we wouldn't need to do unnecessary requests.
class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        # Outer key: <exchange>
        # Inner key: <account>
        self._exchange_accounts: Dict[str, Dict[str, _Account]] = defaultdict(
            lambda: defaultdict(_Account)
        )
        self._sync_tasks: Dict[Tuple[str, str], asyncio.Task] = {}

    async def __aenter__(self) -> Wallet:
        await asyncio.gather(
            self.ensure_sync(self._exchanges.keys(), ['spot']),
            self.ensure_sync(
                (k for k, v in self._exchanges.items() if v.can_margin_trade),
                ['margin'],
            ),
        )
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._sync_tasks.values())

    def get_balance(
        self,
        exchange: str,
        asset: str,
        account: str = 'spot',
    ) -> Balance:
        return self._exchange_accounts[exchange][account].balances[asset]

    # TODO: Find a better solution for keeping local balances up-to-date. Consolidate with
    # `get_balance`.
    async def get_balance2(
        self,
        exchange: str,
        asset: str,
        account: str = 'spot',
    ) -> Balance:
        return (await self._exchanges[exchange].map_balances(account=account))[asset]

    def get_updated_event(
        self,
        exchange: str,
        account: str = 'spot',
    ) -> Event[None]:
        return self._exchange_accounts[exchange][account].updated

    def map_significant_balances(
        self,
        exchange: str,
        account: str = 'spot',
    ) -> Dict[str, Balance]:
        return {
            k: v for k, v in self._exchange_accounts[exchange][account].balances.items()
            if v.significant
        }

    async def transfer(
        self, exchange: str, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        await self._ensure_account(exchange, to_account)
        await self._exchanges[exchange].transfer(
            asset=asset, size=size, from_account=from_account, to_account=to_account
        )

    async def borrow(
        self, exchange: str, asset: str, size: Decimal, account: str = 'margin'
    ) -> None:
        # TODO: Uncomment once we store exchange account state locally.
        # await self._ensure_account(exchange, account)
        await self._exchanges[exchange].borrow(asset=asset, size=size, account=account)

    async def repay(
        self, exchange: str, asset: str, size: Decimal, account: str = 'margin'
    ) -> None:
        # await self._ensure_account(exchange, account)
        await self._exchanges[exchange].repay(asset=asset, size=size, account=account)

    async def get_max_borrowable(
        self, exchange: str, asset: str, account: str = 'margin'
    ) -> Decimal:
        # await self._ensure_account(exchange, account)
        return await self._exchanges[exchange].get_max_borrowable(asset=asset, account=account)

    async def ensure_sync(self, exchanges: Iterable[str], accounts: Iterable[str]) -> None:
        # Only pick products which are not being synced yet.
        products = [
            p for p in product(exchanges, accounts) if p not in self._sync_tasks.keys()
        ]
        if len(products) == 0:
            return

        _log.info(f'syncing {products}')

        # Create accounts where necessary.
        await asyncio.gather(*(self._ensure_account(e, a) for e, a in products))

        # Barrier to wait for initial data to be fetched.
        barrier = SlotBarrier(products)
        for exchange, account in products:
            self._sync_tasks[(exchange, account)] = create_task_cancel_on_exc(
                self._sync_balances(exchange, account, barrier)
            )
        await barrier.wait()

    async def _ensure_account(self, exchange: str, account: str) -> None:
        if account in ['spot', 'margin']:
            return
        try:
            await self._exchanges[exchange].create_account(account)
        except ExchangeException:
            _log.info(f'account {account} already created')

    async def _sync_balances(self, exchange: str, account: str, barrier: SlotBarrier) -> None:
        exchange_wallet = self._exchange_accounts[exchange][account]
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                async for balances in self._stream_balances(exchange, account):
                    _log.info(f'received {account} balance update from {exchange}')
                    exchange_wallet.balances = balances
                    if is_first:
                        is_first = False
                        barrier.release((exchange, account))
                    exchange_wallet.updated.set()

    async def _stream_balances(
        self, exchange: str, account: str
    ) -> AsyncIterable[Dict[str, Balance]]:
        exchange_instance = self._exchanges[exchange]

        if exchange_instance.can_stream_balances:
            # TODO: We are not receiving `interest` nor `borrowed` data through web socket updates.
            # Figure out a better way to handle these.
            async with exchange_instance.connect_stream_balances(account=account) as stream:
                # This is not needed for Binance if it is sending full updates with
                # 'outboundAccountInfo' event type. They will send initial status through
                # websocket. In case of 'outboundAccountPosition' it is required.
                # However, it may be needed for Coinbase or Kraken. If it is, then we should add a
                # new capability `can_stream_initial_balances`.
                # Get initial status from REST API.
                yield await exchange_instance.map_balances(account=account)

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(
                f'{exchange} does not support streaming {account} balances; fething only initial '
                'balances; further updates not implemented'
            )
            yield await exchange_instance.map_balances(account=account)


class _Account:
    def __init__(self) -> None:
        self.balances: Dict[str, Balance] = {}
        self.updated: Event[None] = Event(autoclear=True)
