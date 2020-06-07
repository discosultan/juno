from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, AsyncIterable, Dict, Iterable, List, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Depth, ExchangeException, Fill, Filters, Side
from juno.asyncio import Event, SlotBarrier, cancel, create_task_cancel_on_exc
from juno.config import list_names
from juno.exchanges import Exchange
from juno.math import round_half_up
from juno.tenacity import stop_after_attempt_with_reset
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


class Orderbook:
    def __init__(self, exchanges: List[Exchange], config: Dict[str, Any] = {}) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._symbols = list_names(config, 'symbol')
        self._sync_tasks: Dict[Tuple[str, str], asyncio.Task] = {}

        # {
        #   "binance": {
        #     "eth-btc": {
        #       "asks": {
        #         Decimal('1.0'): Decimal('2.0')
        #       },
        #       "bids": {
        #       }
        #     }
        #   }
        # }
        self._data: Dict[str, Dict[str, _OrderbookData]] = defaultdict(
            lambda: defaultdict(_OrderbookData)
        )

    async def __aenter__(self) -> Orderbook:
        await self.ensure_sync(self._exchanges.keys(), self._symbols)
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._sync_tasks.values())

    def get_updated_event(self, exchange: str, symbol: str) -> Event[None]:
        return self._data[exchange][symbol].updated

    def list_asks(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data[exchange][symbol].sides[Side.BUY].items())

    def list_bids(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data[exchange][symbol].sides[Side.SELL].items(), reverse=True)

    def find_order_asks(
        self, exchange: str, symbol: str, size: Decimal, fee_rate: Decimal, filters: Filters
    ) -> List[Fill]:
        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for aprice, asize in self.list_asks(exchange, symbol):
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
        return result

    def find_order_asks_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, fee_rate: Decimal, filters: Filters
    ) -> List[Fill]:
        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for aprice, asize in self.list_asks(exchange, symbol):
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
        self, exchange: str, symbol: str, size: Decimal, fee_rate: Decimal, filters: Filters
    ) -> List[Fill]:
        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for bprice, bsize in self.list_bids(exchange, symbol):
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

    async def ensure_sync(self, exchanges: Iterable[str], symbols: Iterable[str]) -> None:
        # Only pick products which are not being synced yet.
        products = [
            p for p in product(exchanges, symbols) if p not in self._sync_tasks.keys()
        ]
        if len(products) == 0:
            return

        _log.info(f'syncing {products}')

        # Barrier to wait for initial data to be fetched.
        barrier = SlotBarrier(products)
        for exchange, symbol in products:
            self._sync_tasks[(exchange, symbol)] = create_task_cancel_on_exc(
                self._sync_orderbook(exchange, symbol, barrier)
            )
        await barrier.wait()

    async def _sync_orderbook(self, exchange: str, symbol: str, barrier: SlotBarrier) -> None:
        orderbook = self._data[exchange][symbol]
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                orderbook.snapshot_received = False
                async for depth in self._stream_depth(exchange, symbol):
                    if isinstance(depth, Depth.Snapshot):
                        _set_orderbook_side(orderbook.sides[Side.BUY], depth.asks)
                        _set_orderbook_side(orderbook.sides[Side.SELL], depth.bids)
                        orderbook.snapshot_received = True
                        if barrier.slot_locked((exchange, symbol)):
                            barrier.release((exchange, symbol))
                    elif isinstance(depth, Depth.Update):
                        # TODO: For example, with depth level 10, Kraken expects us to discard
                        # levels outside level 10. They will not publish messages to delete them.
                        assert orderbook.snapshot_received
                        _update_orderbook_side(orderbook.sides[Side.BUY], depth.asks)
                        _update_orderbook_side(orderbook.sides[Side.SELL], depth.bids)
                    else:
                        raise NotImplementedError(depth)
                    orderbook.updated.set()

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


class _OrderbookData:
    def __init__(self) -> None:
        self.sides: Dict[Side, Dict[Decimal, Decimal]] = {
            Side.BUY: {},
            Side.SELL: {},
        }
        self.updated: Event[None] = Event(autoclear=True)
        self.snapshot_received = False
