from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Optional

from asyncstdlib import chain as chain_async
from tenacity import AsyncRetrying, before_sleep_log, retry_if_exception_type

from juno import Depth, ExchangeException, Fill, Filters, Side, Symbol, Symbol_
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, resolved_stream
from juno.exchanges import Exchange
from juno.math import round_half_up
from juno.tenacity import stop_after_attempt_with_reset, wait_none_then_exponential
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class _MissingDepth(Exception):
    """Websocket received an update, but previous update is too old."""

    pass


class _MissingInitialDepth(Exception):
    """Websocket received an update, but REST API snapshot is too old."""

    pass


class Orderbook:
    class SyncContext:
        def __init__(
            self, symbol: Symbol, sides: Optional[dict[Side, dict[Decimal, Decimal]]] = None
        ) -> None:
            self.symbol = symbol
            self.sides = (
                {
                    Side.BUY: {},
                    Side.SELL: {},
                }
                if sides is None
                else sides
            )
            # Will not be set for initial data.
            self.updated: Event[None] = Event(autoclear=True)

        def list_asks(self) -> list[tuple[Decimal, Decimal]]:
            return sorted(self.sides[Side.BUY].items())

        def list_bids(self) -> list[tuple[Decimal, Decimal]]:
            return sorted(self.sides[Side.SELL].items(), reverse=True)

        def find_order_asks(
            self,
            fee_rate: Decimal,
            filters: Filters,
            size: Optional[Decimal] = None,
            quote: Optional[Decimal] = None,
        ) -> list[Fill]:
            if size is not None and quote is not None:
                raise ValueError()
            if size is None and quote is None:
                raise ValueError()

            result = []
            base_asset = Symbol_.base_asset(self.symbol)
            if size is not None:
                for aprice, asize in self.list_asks():
                    if asize >= size:
                        fee = round_half_up(size * fee_rate, filters.base_precision)
                        result.append(
                            Fill.with_computed_quote(
                                price=aprice,
                                size=size,
                                fee=fee,
                                fee_asset=base_asset,
                                precision=filters.quote_precision,
                            )
                        )
                        break
                    else:
                        fee = round_half_up(asize * fee_rate, filters.base_precision)
                        result.append(
                            Fill.with_computed_quote(
                                price=aprice,
                                size=asize,
                                fee=fee,
                                fee_asset=base_asset,
                                precision=filters.quote_precision,
                            )
                        )
                        size -= asize
            elif quote is not None:
                for aprice, asize in self.list_asks():
                    aquote = aprice * asize
                    if aquote >= quote:
                        size = filters.size.round_down(quote / aprice)
                        if size != 0:
                            fee = round_half_up(size * fee_rate, filters.base_precision)
                            result.append(
                                Fill.with_computed_quote(
                                    price=aprice,
                                    size=size,
                                    fee=fee,
                                    fee_asset=base_asset,
                                    precision=filters.quote_precision,
                                )
                            )
                        break
                    else:
                        assert asize != 0
                        fee = round_half_up(asize * fee_rate, filters.base_precision)
                        result.append(
                            Fill.with_computed_quote(
                                price=aprice,
                                size=asize,
                                fee=fee,
                                fee_asset=base_asset,
                                precision=filters.quote_precision,
                            )
                        )
                        quote -= aquote
            return result

        def find_order_bids(
            self,
            fee_rate: Decimal,
            filters: Filters,
            size: Optional[Decimal] = None,
            quote: Optional[Decimal] = None,
        ) -> list[Fill]:
            if quote is not None:
                raise NotImplementedError()
            if size is None:
                raise ValueError()

            result = []
            base_asset, quote_asset = Symbol_.assets(self.symbol)
            for bprice, bsize in self.list_bids():
                if bsize >= size:
                    rsize = filters.size.round_down(size)
                    if size != 0:
                        fee = round_half_up(bprice * rsize * fee_rate, filters.quote_precision)
                        result.append(
                            Fill.with_computed_quote(
                                price=bprice,
                                size=rsize,
                                fee=fee,
                                fee_asset=quote_asset,
                                precision=filters.quote_precision,
                            )
                        )
                    break
                else:
                    assert bsize != 0
                    fee = round_half_up(bprice * bsize * fee_rate, filters.quote_precision)
                    result.append(
                        Fill.with_computed_quote(
                            price=bprice,
                            size=bsize,
                            fee=fee,
                            fee_asset=quote_asset,
                            precision=filters.quote_precision,
                        )
                    )
                    size -= bsize
            return result

    def __init__(self, exchanges: list[Exchange]) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

        # Order sync state.
        # Key: (exchange, symbol)
        self._sync_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._sync_ctxs: dict[tuple[str, str], dict[str, Orderbook.SyncContext]] = defaultdict(
            dict
        )

    async def __aenter__(self) -> Orderbook:
        _log.info("ready")
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        # await cancel(*self._sync_tasks.values())
        pass

    @asynccontextmanager
    async def sync(self, exchange: str, symbol: Symbol) -> AsyncIterator[SyncContext]:
        id_ = str(uuid.uuid4())
        key = (exchange, symbol)
        ctxs = self._sync_ctxs[key]

        if len(ctxs) == 0:
            ctx = Orderbook.SyncContext(symbol)
            ctxs[id_] = ctx
            synced = asyncio.Event()
            self._sync_tasks[key] = create_task_sigint_on_exception(
                self._sync_orderbook(exchange, symbol, synced)
            )
            # TODO: Synced also needs to set in the else clause. Otherwise can run into
            # concurrency issues.
            await synced.wait()
        else:
            ctx = Orderbook.SyncContext(symbol, next(iter(ctxs.values())).sides)
            ctxs[id_] = ctx

        try:
            yield ctx
        finally:
            del ctxs[id_]
            if len(ctxs) == 0:
                task = self._sync_tasks[key]
                del self._sync_tasks[key]
                del self._sync_ctxs[key]
                await asyncio.shield(cancel(task))

    async def _sync_orderbook(self, exchange: str, symbol: Symbol, synced: asyncio.Event) -> None:
        ctxs = self._sync_ctxs[(exchange, symbol)]
        is_first = True
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt_with_reset(8, 300),
            wait=wait_none_then_exponential(),
            retry=retry_if_exception_type((ExchangeException, _MissingDepth)),
            before_sleep=before_sleep_log(_log, logging.WARNING),
        ):
            with attempt:
                async for depth in self._stream_depth(exchange, symbol):
                    if isinstance(depth, Depth.Snapshot):
                        for ctx in ctxs.values():
                            _set_orderbook_side(ctx.sides[Side.BUY], depth.asks)
                            _set_orderbook_side(ctx.sides[Side.SELL], depth.bids)

                        if is_first:
                            is_first = False
                            synced.set()
                        else:
                            for ctx in ctxs.values():
                                ctx.updated.set()
                    elif isinstance(depth, Depth.Update):
                        # TODO: For example, with depth level 10, Kraken expects us to discard
                        # levels outside level 10. They will not publish messages to delete them.
                        assert not is_first
                        for ctx in ctxs.values():
                            _update_orderbook_side(ctx.sides[Side.BUY], depth.asks)
                            _update_orderbook_side(ctx.sides[Side.SELL], depth.bids)

                        for ctx in ctxs.values():
                            ctx.updated.set()
                    else:
                        raise NotImplementedError(depth)

    async def _stream_depth(self, exchange: str, symbol: Symbol) -> AsyncIterable[Depth.Any]:
        exchange_instance = self._exchanges[exchange]

        async with exchange_instance.connect_stream_depth(symbol) as stream:
            if exchange_instance.can_stream_depth_snapshot:
                async for depth in stream:
                    yield depth
            else:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt_with_reset(4, 300),
                    wait=wait_none_then_exponential(),
                    retry=retry_if_exception_type(_MissingInitialDepth),
                    before_sleep=before_sleep_log(_log, logging.WARNING),
                ):
                    with attempt:
                        snapshot = await exchange_instance.get_depth(symbol)
                        yield snapshot

                        is_first = True
                        last_update_id = snapshot.last_id
                        async for update in stream:
                            assert isinstance(update, Depth.Update)

                            if (
                                last_update_id == 0
                                and update.first_id == 0
                                and update.last_id == 0
                            ):
                                yield update
                                continue

                            assert update.last_id >= update.first_id

                            if update.last_id <= last_update_id:
                                _log.debug(
                                    f"skipping {symbol} depth update; {update.last_id=} <= "
                                    f"{last_update_id=}"
                                )
                                continue

                            # Normally `update.first_id` is `last_update_id + 1`. However, during
                            # the initial update, it can be less than that because the snapeshot we
                            # received partially covers the same update region as our update. In
                            # case there's a missing depth update, we retry.
                            if update.first_id > last_update_id + 1:
                                if is_first:
                                    _log.warning(
                                        f"{symbol} orderbook out of sync: {update.first_id=} > "
                                        f"{last_update_id=} + 1; retrying fetching snapshot"
                                    )
                                    # Put the current update back into the stream.
                                    stream = chain_async(resolved_stream(update), stream)
                                    raise _MissingInitialDepth()
                                else:
                                    _log.warning(
                                        f"{symbol} orderbook out of sync: {update.first_id=} > "
                                        f"{last_update_id=} + 1; retrying from scratch"
                                    )
                                    raise _MissingDepth()

                            yield update
                            last_update_id = update.last_id
                            is_first = False


def _set_orderbook_side(
    orderbook_side: dict[Decimal, Decimal], values: list[tuple[Decimal, Decimal]]
) -> None:
    orderbook_side.clear()
    for price, size in values:
        orderbook_side[price] = size


def _update_orderbook_side(
    orderbook_side: dict[Decimal, Decimal], values: list[tuple[Decimal, Decimal]]
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
