from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import DepthUpdateType, Side
from juno.asyncio import Barrier, Event, cancel, cancelable
from juno.config import list_names
from juno.exchanges import Exchange
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)


class Orderbook:
    def __init__(self, exchanges: List[Exchange], config: Dict[str, Any]) -> None:
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
        self._data: Dict[str, Dict[str, _OrderbookData]] = defaultdict(
            lambda: defaultdict(_OrderbookData)
        )

    async def __aenter__(self) -> Orderbook:
        self._initial_orderbook_fetched = Barrier(len(self._orderbooks_product))
        self._sync_task = asyncio.create_task(cancelable(self._sync_orderbooks()))
        await self._initial_orderbook_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_task)

    def get_updated_event(self, exchange: str, symbol: str) -> Event[None]:
        return self._data[exchange][symbol].updated

    def list_asks(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data[exchange][symbol][Side.BID].items())

    def list_bids(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data[exchange][symbol][Side.ASK].items(), reverse=True)

    async def _sync_orderbooks(self) -> None:
        await asyncio.gather(
            *(self._sync_orderbook(e, s) for e, s in self._orderbooks_product)
        )

    async def _sync_orderbook(self, exchange: str, symbol: str) -> None:
        orderbook = self._data[exchange][symbol]
        async with self._exchanges[exchange].connect_stream_depth(symbol) as stream:
            async for depth_update in stream:
                if depth_update.type is DepthUpdateType.SNAPSHOT:
                    orderbook[Side.BID] = {k: v for k, v in depth_update.asks}
                    orderbook[Side.ASK] = {k: v for k, v in depth_update.bids}
                    orderbook.snapshot_received = True
                    self._initial_orderbook_fetched.release()
                elif depth_update.type is DepthUpdateType.UPDATE:
                    assert orderbook.snapshot_received
                    _update_orderbook_side(orderbook[Side.BID], depth_update.asks)
                    _update_orderbook_side(orderbook[Side.ASK], depth_update.bids)
                else:
                    raise NotImplementedError()
                orderbook.updated.set()


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


class _OrderbookData(Dict[Side, Dict[Decimal, Decimal]]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.updated: Event[None] = Event(autoclear=True)
        self.snapshot_received = False
