from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Dict, List, Optional, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Depth, ExchangeException, Fill, Filters, Side
from juno.asyncio import Event, cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.math import round_half_up
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


class Orderbook:
    # TODO: Separate context per consumer? Can remove RCs this way as well.
    class SyncContext:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self.sides: Dict[Side, Dict[Decimal, Decimal]] = {
                Side.BUY: {},
                Side.SELL: {},
            }
            # Will not be set for initial data.
            self.updated: Event[None] = Event(autoclear=True)

        def clear(self) -> None:
            self.updated.clear()

        def list_asks(self) -> List[Tuple[Decimal, Decimal]]:
            return sorted(self.sides[Side.BUY].items())

        def list_bids(self) -> List[Tuple[Decimal, Decimal]]:
            return sorted(self.sides[Side.SELL].items(), reverse=True)

        def find_order_asks(
            self,
            fee_rate: Decimal,
            filters: Filters,
            size: Optional[Decimal] = None,
            quote: Optional[Decimal] = None,
        ) -> List[Fill]:
            if size is not None and quote is not None:
                raise ValueError()
            if size is None and quote is None:
                raise ValueError()

            result = []
            base_asset, quote_asset = unpack_symbol(self.symbol)
            if size is not None:
                for aprice, asize in self.list_asks():
                    if asize >= size:
                        fee = round_half_up(size * fee_rate, filters.base_precision)
                        result.append(Fill.with_computed_quote(
                            price=aprice, size=size, fee=fee, fee_asset=base_asset,
                            precision=filters.quote_precision
                        ))
                        break
                    else:
                        fee = round_half_up(asize * fee_rate, filters.base_precision)
                        result.append(Fill.with_computed_quote(
                            price=aprice, size=asize, fee=fee, fee_asset=base_asset,
                            precision=filters.quote_precision
                        ))
                        size -= asize
            elif quote is not None:
                for aprice, asize in self.list_asks():
                    aquote = aprice * asize
                    if aquote >= quote:
                        size = filters.size.round_down(quote / aprice)
                        if size != 0:
                            fee = round_half_up(size * fee_rate, filters.base_precision)
                            result.append(Fill.with_computed_quote(
                                price=aprice, size=size, fee=fee, fee_asset=base_asset,
                                precision=filters.quote_precision
                            ))
                        break
                    else:
                        assert asize != 0
                        fee = round_half_up(asize * fee_rate, filters.base_precision)
                        result.append(Fill.with_computed_quote(
                            price=aprice, size=asize, fee=fee, fee_asset=base_asset,
                            precision=filters.quote_precision
                        ))
                        quote -= aquote
            return result

        def find_order_bids(
            self,
            fee_rate: Decimal,
            filters: Filters,
            size: Optional[Decimal] = None,
            quote: Optional[Decimal] = None,
        ) -> List[Fill]:
            if quote is not None:
                raise NotImplementedError()
            if size is None:
                raise ValueError()

            result = []
            base_asset, quote_asset = unpack_symbol(self.symbol)
            for bprice, bsize in self.list_bids():
                if bsize >= size:
                    rsize = filters.size.round_down(size)
                    if size != 0:
                        fee = round_half_up(bprice * rsize * fee_rate, filters.quote_precision)
                        result.append(Fill.with_computed_quote(
                            price=bprice, size=rsize, fee=fee, fee_asset=quote_asset,
                            precision=filters.quote_precision
                        ))
                    break
                else:
                    assert bsize != 0
                    fee = round_half_up(bprice * bsize * fee_rate, filters.quote_precision)
                    result.append(Fill.with_computed_quote(
                        price=bprice, size=bsize, fee=fee, fee_asset=quote_asset,
                        precision=filters.quote_precision
                    ))
                    size -= bsize
            return result

    def __init__(self, exchanges: List[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

        # Order sync state.
        # Key: (exchange, symbol)
        self._sync_tasks: Dict[Tuple[str, str], asyncio.Task] = {}
        self._sync_ctxs: Dict[Tuple[str, str], Orderbook.SyncContext] = {}
        self._sync_counters: Dict[Tuple[str, str], int] = defaultdict(int)

    async def __aenter__(self) -> Orderbook:
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._sync_tasks.values())

    def can_place_order_market_quote(self, exchange: str) -> bool:
        if exchange == '__all__':
            return all(e.can_place_order_market_quote for e in self._exchanges.values())
        return self._exchanges[exchange].can_place_order_market_quote

    @asynccontextmanager
    async def sync(self, exchange: str, symbol: str) -> AsyncIterator[SyncContext]:
        key = (exchange, symbol)
        if not (ctx := self._sync_ctxs.get(key)):
            ctx = Orderbook.SyncContext(symbol)
            self._sync_ctxs[key] = ctx

        if self._sync_counters[key] == 0:
            self._sync_counters[key] += 1
            synced = asyncio.Event()
            self._sync_tasks[key] = create_task_cancel_on_exc(
                self._sync_orderbook(exchange, symbol, synced)
            )
            await synced.wait()
        else:
            self._sync_counters[key] += 1

        try:
            yield ctx
        finally:
            self._sync_counters[key] -= 1
            if self._sync_counters[key] == 0:
                ctx.clear()
                await cancel(self._sync_tasks[key])

    async def _sync_orderbook(self, exchange: str, symbol: str, synced: asyncio.Event) -> None:
        ctx = self._sync_ctxs[(exchange, symbol)]
        is_first = True
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                async for depth in self._stream_depth(exchange, symbol):
                    if isinstance(depth, Depth.Snapshot):
                        _set_orderbook_side(ctx.sides[Side.BUY], depth.asks)
                        _set_orderbook_side(ctx.sides[Side.SELL], depth.bids)
                        if is_first:
                            is_first = False
                            synced.set()
                        else:
                            ctx.updated.set()
                    elif isinstance(depth, Depth.Update):
                        # TODO: For example, with depth level 10, Kraken expects us to discard
                        # levels outside level 10. They will not publish messages to delete them.
                        assert not is_first
                        _update_orderbook_side(ctx.sides[Side.BUY], depth.asks)
                        _update_orderbook_side(ctx.sides[Side.SELL], depth.bids)
                        ctx.updated.set()
                    else:
                        raise NotImplementedError(depth)

    async def _stream_depth(self, exchange: str, symbol: str) -> AsyncIterable[Depth.Any]:
        exchange_instance = self._exchanges[exchange]

        while True:
            restart = False

            async with exchange_instance.connect_stream_depth(symbol) as stream:
                if exchange_instance.can_stream_depth_snapshot:
                    async for depth in stream:
                        yield depth
                else:
                    snapshot = await exchange_instance.get_depth(symbol)
                    yield snapshot

                    last_update_id = snapshot.last_id
                    is_first_update = True
                    async for update in stream:
                        assert isinstance(update, Depth.Update)

                        if last_update_id == 0 and update.first_id == 0 and update.last_id == 0:
                            yield update
                            continue

                        if update.last_id <= last_update_id:
                            _log.debug(
                                f'skipping depth update; {update.last_id=} <= '
                                f'{last_update_id=}'
                            )
                            continue

                        if is_first_update:
                            assert (
                                update.first_id <= last_update_id + 1
                                and update.last_id >= last_update_id + 1
                            )
                            is_first_update = False
                        elif update.first_id != last_update_id + 1:
                            _log.warning(
                                f'orderbook out of sync: {update.first_id=} != {last_update_id=} '
                                '+ 1; refetching snapshot'
                            )
                            restart = True
                            break

                        yield update
                        last_update_id = update.last_id

            if not restart:
                break


def _set_orderbook_side(
    orderbook_side: Dict[Decimal, Decimal], values: List[Tuple[Decimal, Decimal]]
) -> None:
    orderbook_side.clear()
    for price, size in values:
        orderbook_side[price] = size


def _update_orderbook_side(
    orderbook_side: Dict[Decimal, Decimal], values: List[Tuple[Decimal, Decimal]]
) -> None:
    for price, size in values:
        if size > 0:
            orderbook_side[price] = size
        elif price in orderbook_side:
            del orderbook_side[price]
        else:
            # Receiving an event that removes a price level that is not in the local orderbook can
            # happen and is normal for Binance, for example.
            pass
