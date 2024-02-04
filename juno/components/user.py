from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import AsyncIterable, AsyncIterator, Optional

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from juno import (
    Account,
    Asset,
    Balance,
    ExchangeException,
    OrderResult,
    OrderType,
    OrderUpdate,
    SavingsProduct,
    Side,
    Symbol,
    TimeInForce,
)
from juno.asyncio import Event, cancel, create_task_sigint_on_exception
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset

_log = logging.getLogger(__name__)


class User:
    class WalletSyncContext:
        def __init__(self, balances: Optional[dict[Asset, Balance]] = None) -> None:
            self.balances = {} if balances is None else balances
            # Will not be set for initial data.
            self.updated: Event[None] = Event(autoclear=True)

    def __init__(self, exchanges: list[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._open_accounts: dict[str, set[str]] = {}

        # Balance sync state.
        # Key: (exchange, account)
        self._wallet_sync_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._wallet_sync_ctxs: dict[tuple[str, str], dict[str, User.WalletSyncContext]] = (
            defaultdict(dict)
        )

    async def __aenter__(self) -> User:
        _log.info("ready")
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await cancel(*self._wallet_sync_tasks.values())

    def generate_client_id(self, exchange: str) -> str:
        return self._exchanges[exchange].generate_client_id()

    def can_place_market_order(self, exchange: str) -> bool:
        if exchange == "__all__":
            return all(e.can_place_market_order for e in self._exchanges.values())
        return self._exchanges[exchange].can_place_market_order

    def can_place_market_order_quote(self, exchange: str) -> bool:
        if exchange == "__all__":
            return all(e.can_place_market_order_quote for e in self._exchanges.values())
        return self._exchanges[exchange].can_place_market_order_quote

    def can_get_market_order_result_direct(self, exchange: str) -> bool:
        if exchange == "__all__":
            return all(e.can_get_market_order_result_direct for e in self._exchanges.values())
        return self._exchanges[exchange].can_get_market_order_result_direct

    @asynccontextmanager
    async def sync_wallet(
        self, exchange: str, account: Account
    ) -> AsyncIterator[WalletSyncContext]:
        id_ = str(uuid.uuid4())
        key = (exchange, account)
        ctxs = self._wallet_sync_ctxs[key]

        if len(ctxs) == 0:
            ctx = User.WalletSyncContext()
            ctxs[id_] = ctx
            synced = asyncio.Event()
            self._wallet_sync_tasks[key] = create_task_sigint_on_exception(
                self._sync_balances(exchange, account, synced)
            )
            await synced.wait()
        else:
            ctx = User.WalletSyncContext(next(iter(ctxs.values())).balances)
            ctxs[id_] = ctx
            # TODO: We also need to wait for initial sync here. Add a test for it.

        try:
            yield ctx
        finally:
            del ctxs[id_]
            if len(ctxs) == 0:
                await cancel(self._wallet_sync_tasks[key])

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def get_balance(
        self,
        exchange: str,
        account: Account,
        asset: Asset,
    ) -> Balance:
        if account == "isolated":
            raise ValueError("Ambiguous account: isolated")
        # Currently, for Binance, we need to put all isolated margin accounts into an umbrella
        # 'isolated' account when requesting balances.
        account_arg = account if account in {"spot", "margin"} else "isolated"
        return (await self._exchanges[exchange].map_balances(account=account_arg))[account].get(
            asset, Balance.zero()
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def map_balances(
        self,
        exchange: str,
        accounts: list[Account],
        significant: Optional[bool] = None,
    ) -> dict[Account, dict[Asset, Balance]]:
        account_args = {(a if a in {"spot", "margin"} else "isolated") for a in accounts}

        exchange_instance = self._exchanges[exchange]
        result: dict[Account, dict[Asset, Balance]] = {}
        balances = await asyncio.gather(
            *(exchange_instance.map_balances(account=a) for a in account_args)
        )
        for balance in balances:
            result.update(balance)
        if "isolated" not in accounts:
            for key in list(result.keys()):
                if key not in accounts:
                    del result[key]
        # Filtering.
        if significant is not None:
            result = {
                k: {a: b for a, b in v.items() if b.significant == significant}
                for k, v in result.items()
            }
        return result

    @asynccontextmanager
    async def connect_stream_orders(
        self, exchange: str, account: Account, symbol: Symbol
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt_with_reset(8, 300),
            wait=wait_exponential(),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING),
        ):
            with attempt:
                async with self._exchanges[exchange].connect_stream_orders(
                    account=account,
                    symbol=symbol,
                ) as stream:
                    yield stream

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def place_order(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
        leverage: Optional[int] = None,
        reduce_only: Optional[bool] = None,
    ) -> OrderResult:
        return await self._exchanges[exchange].place_order(
            account=account,
            symbol=symbol,
            side=side,
            type_=type_,
            size=size,
            quote=quote,
            price=price,
            time_in_force=time_in_force,
            client_id=client_id,
            leverage=leverage,
            reduce_only=reduce_only,
        )

    def can_edit_order(self, exchange: str) -> bool:
        return self._exchanges[exchange].can_edit_order

    def can_edit_order_atomic(self, exchange: str) -> bool:
        return self._exchanges[exchange].can_edit_order_atomic

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def edit_order(
        self,
        existing_id: str,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        exchange_instance = self._exchanges[exchange]
        if not exchange_instance.can_edit_order:
            raise RuntimeError("Not supported")
        return await exchange_instance.edit_order(
            existing_id=existing_id,
            account=account,
            symbol=symbol,
            side=side,
            type_=type_,
            size=size,
            quote=quote,
            price=price,
            time_in_force=time_in_force,
            client_id=client_id,
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def cancel_order(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        client_id: str,
    ) -> None:
        await self._exchanges[exchange].cancel_order(
            account=account,
            symbol=symbol,
            client_id=client_id,
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def transfer(
        self,
        exchange: str,
        asset: Asset,
        size: Decimal,
        from_account: Account,
        to_account: Account,
    ) -> None:
        await self._exchanges[exchange].transfer(
            asset=asset, size=size, from_account=from_account, to_account=to_account
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def borrow(self, exchange: str, asset: Asset, size: Decimal, account: Account) -> None:
        await self._exchanges[exchange].borrow(asset=asset, size=size, account=account)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def repay(self, exchange: str, asset: Asset, size: Decimal, account: Account) -> None:
        await self._exchanges[exchange].repay(asset=asset, size=size, account=account)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def get_max_borrowable(self, exchange: str, asset: Asset, account: Account) -> Decimal:
        return await self._exchanges[exchange].get_max_borrowable(asset=asset, account=account)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def map_savings_products(
        self,
        exchange: str,
        asset: Optional[Asset] = None,
    ) -> dict[str, SavingsProduct]:
        return await self._exchanges[exchange].map_savings_products(asset=asset)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def purchase_savings_product(
        self,
        exchange: str,
        product_id: str,
        size: Decimal,
    ) -> None:
        return await self._exchanges[exchange].purchase_savings_product(product_id, size)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def redeem_savings_product(self, exchange: str, product_id: str, size: Decimal) -> None:
        return await self._exchanges[exchange].redeem_savings_product(product_id, size)

    async def _sync_balances(self, exchange: str, account: Account, synced: asyncio.Event) -> None:
        ctxs = self._wallet_sync_ctxs[(exchange, account)]
        is_first = True
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt_with_reset(8, 300),
            wait=wait_exponential(),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING),
        ):
            with attempt:
                async for balances in self._stream_balances(exchange, account):
                    _log.info(f"received {exchange} {account} balance update")
                    for ctx in ctxs.values():
                        ctx.balances.update(balances)

                    if is_first:
                        is_first = False
                        synced.set()
                    else:
                        for ctx in ctxs.values():
                            ctx.updated.set()

    async def _stream_balances(
        self, exchange: str, account: Account
    ) -> AsyncIterable[dict[str, Balance]]:
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
                f"{exchange} does not support streaming {account} balances; fething only initial "
                "balances; further updates not implemented"
            )
            yield (await exchange_instance.map_balances(account))[account]
