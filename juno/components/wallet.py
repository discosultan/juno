from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterable, Dict, List

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Balance, JunoException, MarginBalance
from juno.asyncio import Barrier, cancel, cancelable
from juno.exchanges import Exchange
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Wallet:
    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._exchange_balances: Dict[str, Dict[str, Balance]] = defaultdict(dict)
        self._exchange_margin_balances: Dict[str, Dict[str, MarginBalance]] = defaultdict(dict)

    async def __aenter__(self) -> Wallet:
        self._initial_balances_fetched = Barrier(len(self._exchanges))
        self._initial_margin_balances_fetched = Barrier(
            len([e for e in self._exchanges.values() if e.can_margin_trade])
        )
        self._sync_all_balances_task = asyncio.create_task(cancelable(self._sync_all_balances()))
        await asyncio.gather(
            self._initial_balances_fetched.wait(),
            self._initial_margin_balances_fetched.wait(),
        )
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_all_balances_task)

    def get_balance(self, exchange: str, asset: str) -> Balance:
        return self._exchange_balances[exchange][asset]

    def get_margin_balance(self, exchange: str, asset: str) -> MarginBalance:
        return self._exchange_margin_balances[exchange][asset]

    async def _sync_all_balances(self) -> None:
        await asyncio.gather(
            *(self._sync_balances(e) for e in self._exchanges.keys()),
            *(
                self._sync_margin_balances(e) for e, inst in self._exchanges.items()
                if inst.can_margin_trade
            ),
        )

    async def _sync_balances(self, exchange: str) -> None:
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(JunoException),
            before_sleep=before_sleep_log(_log, logging.DEBUG)
        ):
            with attempt:
                async for balances in self._stream_balances(exchange):
                    _log.info(f'received balance update from {exchange}')
                    self._exchange_balances[exchange] = balances
                    if is_first:
                        is_first = False
                        self._initial_balances_fetched.release()

    async def _sync_margin_balances(self, exchange: str) -> None:
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(JunoException),
            before_sleep=before_sleep_log(_log, logging.DEBUG)
        ):
            with attempt:
                async for balances in self._stream_margin_balances(exchange):
                    _log.info(f'received margin balance update from {exchange}')
                    self._exchange_margin_balances[exchange] = balances
                    if is_first:
                        is_first = False
                        self._initial_margin_balances_fetched.release()

    async def _stream_balances(self, exchange: str) -> AsyncIterable[Dict[str, Balance]]:
        exchange_instance = self._exchanges[exchange]

        if exchange_instance.can_stream_balances:
            async with exchange_instance.connect_stream_balances() as stream:
                # Get initial status from REST API.
                yield await exchange_instance.get_balances()

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(f'{exchange} does not support streaming balances; fething only initial '
                         'balances; further updates not implemented')
            yield await exchange_instance.get_balances()

    async def _stream_margin_balances(
        self, exchange: str
    ) -> AsyncIterable[Dict[str, MarginBalance]]:
        exchange_instance = self._exchanges[exchange]

        if exchange_instance.can_stream_balances:
            async with exchange_instance.connect_stream_margin_balances() as stream:
                # Get initial status from REST API.
                yield await exchange_instance.get_margin_balances()

                # Stream future updates over WS.
                async for balances in stream:
                    yield balances
        else:
            _log.warning(f'{exchange} does not support streaming margin balances; fething only '
                         'initial balances; further updates not implemented')
            yield await exchange_instance.get_margin_balances()
