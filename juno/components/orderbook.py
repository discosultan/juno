from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import SymbolInfo
from juno.config import list_required_names
from juno.exchanges import Exchange
from juno.math import adjust_size
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import Barrier

_log = logging.getLogger(__name__)

Trades = List[Tuple[Decimal, Decimal]]


class Orderbook:

    def __init__(self, services: Dict[str, Any], config: Dict[str, Any]) -> None:
        self._exchanges: Dict[str, Exchange] = {
            k: v for k, v in services.items() if isinstance(v, Exchange)}
        self._symbols = list_required_names(config, 'symbol')
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
        self._orderbooks: Dict[str, Dict[str, Dict[str, Dict[Decimal, Decimal]]]] = (
            defaultdict(lambda: defaultdict(dict)))

    async def __aenter__(self) -> Orderbook:
        self._initial_orderbook_fetched = Barrier(len(self._orderbooks_product))
        self._sync_task = asyncio.create_task(self._sync_orderbooks())
        await self._initial_orderbook_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        self._sync_task.cancel()
        await self._sync_task

    def find_market_order_asks(self, exchange: str, symbol: str, quote: Decimal,
                               symbol_info: SymbolInfo) -> Trades:
        result: Trades = []
        asks = self._orderbooks[exchange][symbol]['asks']
        for aprice, asize in sorted(asks.items()):
            aquote = aprice * asize
            if aquote >= quote:
                size = adjust_size(quote / aprice, symbol_info.min_size, symbol_info.max_size,
                                   symbol_info.size_step)
                result.append((aprice, size))
                break
            else:
                result.append((aprice, asize))
                quote -= aquote
        return result

        # total_size = Decimal(0)
        # available_quote = quote_balance
        # for price, size in sorted(asks.items()):
        #     cost = price * size
        #     if cost > available_quote:
        #         fill = floor_multiple(available_quote / price, size_step)
        #         available_quote -= fill * price
        #         total_size += fill
        #         break
        #     else:
        #         total_size += size
        #         available_quote -= cost
        # total_size = adjust_qty(size * percent, ap_info)
        # return total_size

    def find_market_order_bids(self, exchange: str, symbol: str, base: Decimal,
                               symbol_info: SymbolInfo) -> Trades:
        result: Trades = []
        asks = self._orderbooks[exchange][symbol]['bids']
        for bprice, bsize in sorted(asks.items(), reverse=True):
            if bsize >= base:
                size = adjust_size(base, symbol_info.min_size, symbol_info.max_size,
                                   symbol_info.size_step)
                result.append((bprice, size))
                break
            else:
                result.append((bprice, bsize))
                base -= bsize
        return result

        # result = []
        # bids = self._orderbooks[exchange][symbol]['bids']
        # available_base = base_balance
        # for _price, size in sorted(bids.items(), reverse=True):
        #     if size > available_base:
        #         fill = floor_multiple(available_base, size_step)
        #         available_base -= fill
        #         break
        #     else:
        #         available_base -= size
        # total_size = base_balance - available_base
        # # total_size = adjust_qty(size * percent, ap_info)
        # return total_size

    async def _sync_orderbooks(self) -> None:
        try:
            await asyncio.gather(
                *(self._sync_orderbook(e, s) for e, s in self._orderbooks_product))
        except asyncio.CancelledError:
            _log.info('orderbook sync task cancelled')

    async def _sync_orderbook(self, exchange: str, symbol: str) -> None:
        snapshot_received = False
        async for val in self._exchanges[exchange].stream_depth(symbol):
            if val['type'] == 'snapshot':
                snapshot_received = True
                orderbook = {
                    'bids': {k: v for k, v in val['bids']},
                    'asks': {k: v for k, v in val['asks']}
                }
                self._orderbooks[exchange][symbol] = orderbook
                self._initial_orderbook_fetched.release()
            elif val['type'] == 'update':
                assert snapshot_received
                _update_orderbook_side(orderbook['bids'], val['bids'])
                _update_orderbook_side(orderbook['asks'], val['asks'])
            else:
                raise NotImplementedError()


def _update_orderbook_side(orderbook_side: Dict[Decimal, Decimal],
                           values: List[Tuple[Decimal, Decimal]]) -> None:
    for price, size in values:
        if size == 0 and price in orderbook_side:
            del orderbook_side[price]
        else:
            orderbook_side[price] = size
