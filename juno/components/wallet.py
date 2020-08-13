from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterable, Dict, List

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Balance, ExchangeException
from juno.asyncio import Event, SlotBarrier, cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        # Outer key: <exchange>
        # Inner key: '__spot__' | '__cross_margin__' | <isolated_symbol>
        self._exchange_wallets: Dict[str, Dict[str, _ExchangeWallet]] = defaultdict(
            lambda: defaultdict(_ExchangeWallet)
        )

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = SlotBarrier(
            [(e, 'spot') for e in self._exchanges.keys()]
            + [
                (e, 'margin') for e, i
                in self._exchanges.items()
                if i.can_margin_trade
            ]
        )
        self._sync_all_balances_task = create_task_cancel_on_exc(self._sync_all_balances())
        await self._initial_balances_fetched.wait()
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_all_balances_task)

    def get_balance(
        self,
        exchange: str,
        asset: str,
        account: str = 'spot',
    ) -> Balance:
        return self._get_exchange_wallet(exchange, account).balances[asset]

    def get_updated_event(
        self,
        exchange: str,
        account: str = 'spot',
    ) -> Event[None]:
        return self._get_exchange_wallet(exchange, account).updated

    def map_significant_balances(
        self,
        exchange: str,
        account: str = 'spot',
    ) -> Dict[str, Balance]:
        # TODO: Support mapping from all isolated account. We should create a different method
        # because the return type differs: Dict[str, Dict[str, Balance]].
        exchange_wallet = self._get_exchange_wallet(exchange, account)
        return {k: v for k, v in exchange_wallet.balances.items() if v.significant}

    async def _sync_all_balances(self) -> None:
        await asyncio.gather(
            *(self._sync_balances(e, 'spot') for e in self._exchanges.keys()),
            *(
                self._sync_balances(e, 'margin') for e, inst
                in self._exchanges.items()
                if inst.can_margin_trade
            ),
        )

    def _get_exchange_wallet(self, exchange: str, account: str) -> _ExchangeWallet:
        return self._exchange_wallets[exchange][account]

    async def _sync_balances(self, exchange: str, account: str) -> None:
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                if account in ['spot', 'margin']:
                    exchange_wallet = self._get_exchange_wallet(exchange, account)
                    async for balances in self._stream_balances(exchange, account):
                        _log.info(f'received {account.name} balance update from {exchange}')
                        exchange_wallet.balances = balances
                        if is_first:
                            is_first = False
                            self._initial_balances_fetched.release((exchange, account))
                        exchange_wallet.updated.set()
                else:
                    # async for balances in self._stream_
                    pass

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
                yield await exchange_instance.map_balances(
                    margin=account is AccountType.CROSS_MARGIN
                )

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(
                f'{exchange} does not support streaming {account.name} balances; fething only '
                'initial balances; further updates not implemented'
            )
            yield await exchange_instance.map_balances(margin=account is AccountType.CROSS_MARGIN)

    # async def _stream_isolated_margin_balances(self, exchange: str) -> I


class _ExchangeWallet:
    def __init__(self) -> None:
        self.balances: Dict[str, Balance] = {}
        self.updated: Event[None] = Event(autoclear=True)
