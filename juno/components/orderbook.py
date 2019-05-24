from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import DepthUpdateType, Fill, Fills
from juno.asyncio import Barrier, Event
from juno.components import Informant
from juno.config import list_names
from juno.exchanges import Exchange
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


class _Orderbook(Dict[str, Dict[Decimal, Decimal]]):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.updated: Event[None] = Event(autoclear=True)
        self.snapshot_received = False


class Orderbook:

    def __init__(self, informant: Informant, exchanges: List[Exchange], config: Dict[str, Any]
                 ) -> None:
        self._informant = informant
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._symbols = list_names(config, 'symbol')
        self._orderbooks_product = list(product(self._exchanges.keys(), self._symbols))

        # {
        #   "binance": {
        #     "eth-btc": {
        #       "asks": {
        #         Decimal(1): Decimal(2)
        #       },
        #       "bids": {
        #       }
        #     }
        #   }
        # }
        self._orderbooks: Dict[str, Dict[str, _Orderbook]] = defaultdict(
            lambda: defaultdict(_Orderbook))

    async def __aenter__(self) -> Orderbook:
        self._initial_orderbook_fetched = Barrier(len(self._orderbooks_product))
        self._sync_task = asyncio.create_task(self._sync_orderbooks())
        await self._initial_orderbook_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        self._sync_task.cancel()
        await self._sync_task

    def get_orderbook_updated(self, exchange: str, symbol: str) -> Event[None]:
        return self._orderbooks[exchange][symbol].updated

    def list_asks(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._orderbooks[exchange][symbol]['asks'].items())

    def list_bids(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._orderbooks[exchange][symbol]['bids'].items(), reverse=True)

    def find_order_asks(self, exchange: str, symbol: str, quote: Decimal) -> Fills:
        result = Fills()
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        for aprice, asize in self.list_asks(exchange, symbol):
            aquote = aprice * asize
            base_asset, quote_asset = unpack_symbol(symbol)
            if aquote >= quote:
                size = filters.size.round_down(quote / aprice)
                if size != Decimal(0):
                    # TODO: Fee should also be rounded.
                    fee = aprice * size * fees.taker
                    result.append(Fill(price=aprice, size=size, fee=fee, fee_asset=base_asset))
                break
            else:
                assert asize != Decimal(0)
                fee = aprice * asize * fees.taker
                result.append(Fill(price=aprice, size=asize, fee=fee, fee_asset=base_asset))
                quote -= aquote
        return result

    def find_order_bids(self, exchange: str, symbol: str, base: Decimal) -> Fills:
        result = Fills()
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        for bprice, bsize in self.list_bids(exchange, symbol):
            base_asset, quote_asset = unpack_symbol(symbol)
            if bsize >= base:
                size = filters.size.round_down(base)
                if size != Decimal(0):
                    fee = bprice * size * fees.taker
                    result.append(Fill(price=bprice, size=size, fee=fee, fee_asset=quote_asset))
                break
            else:
                assert bsize != Decimal(0)
                fee = bprice * bsize * fees.taker
                result.append(Fill(price=bprice, size=bsize, fee=fee, fee_asset=quote_asset))
                base -= bsize
        return result

    async def _sync_orderbooks(self) -> None:
        try:
            await asyncio.gather(
                *(self._sync_orderbook(e, s) for e, s in self._orderbooks_product))
        except asyncio.CancelledError:
            _log.info('orderbook sync task cancelled')
        except Exception:
            _log.exception('unhandled exception in orderbook sync task')
            raise

    async def _sync_orderbook(self, exchange: str, symbol: str) -> None:
        orderbook = self._orderbooks[exchange][symbol]
        async with self._exchanges[exchange].stream_depth(symbol) as depth_stream:
            async for val in depth_stream:
                if val.type is DepthUpdateType.SNAPSHOT:
                    orderbook['bids'] = {k: v for k, v in val.bids}
                    orderbook['asks'] = {k: v for k, v in val.asks}
                    orderbook.snapshot_received = True
                    self._initial_orderbook_fetched.release()
                elif val.type is DepthUpdateType.UPDATE:
                    assert orderbook.snapshot_received
                    _update_orderbook_side(orderbook['bids'], val.bids)
                    _update_orderbook_side(orderbook['asks'], val.asks)
                else:
                    raise NotImplementedError()
                orderbook.updated.set()


def _update_orderbook_side(orderbook_side: Dict[Decimal, Decimal],
                           values: List[Tuple[Decimal, Decimal]]) -> None:
    for price, size in values:
        if size > 0:
            orderbook_side[price] = size
        elif price in orderbook_side:
            del orderbook_side[price]
        else:
            # Receiving an event that removes a price level that is not in the local orderbook can
            # happen and is normal for Binance, for example.
            pass
