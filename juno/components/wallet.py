from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterable, Dict, List, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Balance, ExchangeException
from juno.asyncio import Barrier, Event, cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        # Key: (exchange, margin)
        self._data: Dict[Tuple[str, bool], _WalletData] = defaultdict(_WalletData)

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = Barrier(
            len(self._exchanges) + len([e for e in self._exchanges.values() if e.can_margin_trade])
        )
        self._sync_all_balances_task = create_task_cancel_on_exc(self._sync_all_balances())
        await self._initial_balances_fetched.wait()
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_all_balances_task)

    def get_balance(self, exchange: str, asset: str, margin: bool = False) -> Balance:
        return self._data[(exchange, margin)].balances[asset]

    def get_updated_event(self, exchange: str, margin: bool = False) -> Event[None]:
        return self._data[(exchange, margin)].updated

    async def _sync_all_balances(self) -> None:
        await asyncio.gather(
            *(self._sync_balances(e, False) for e in self._exchanges.keys()),
            *(
                self._sync_balances(e, True) for e, inst in self._exchanges.items()
                if inst.can_margin_trade
            ),
        )

    async def _sync_balances(self, exchange: str, margin: bool) -> None:
        exchange_data = self._data[(exchange, margin)]
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.DEBUG)
        ):
            with attempt:
                async for balances in self._stream_balances(exchange, margin):
                    _log.info(
                        f'received {"margin" if margin else "spot"} balance update from {exchange}'
                    )
                    exchange_data.balances = balances
                    if is_first:
                        is_first = False
                        self._initial_balances_fetched.release()
                    exchange_data.updated.set()

    async def _stream_balances(
        self, exchange: str, margin: bool
    ) -> AsyncIterable[Dict[str, Balance]]:
        exchange_instance = self._exchanges[exchange]

        if exchange_instance.can_stream_balances:
            # TODO: We are not receiving `interest` nor `borrowed` data through web socket updates.
            # Figure out a better way to handle these.
            async with exchange_instance.connect_stream_balances(margin=margin) as stream:
                # This is not needed for Binance if it is sending full updates with
                # 'outboundAccountInfo' event type. They will send initial status through
                # websocket. In case of 'outboundAccountPosition' it is
                # required.
                # However, it may be needed for Coinbase or Kraken. If it is, then we
                # should add a new capability `can_stream_initial_balances`.
                # Get initial status from REST API.
                yield await exchange_instance.get_balances(margin=margin)

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(
                f'{exchange} does not support streaming {"margin" if margin else "spot"} '
                'balances; fething only initial balances; further updates not implemented'
            )
            yield await exchange_instance.get_balances(margin=margin)


class _WalletData:
    def __init__(self) -> None:
        self.balances: Dict[str, Balance] = {}
        self.updated: Event[None] = Event(autoclear=True)
