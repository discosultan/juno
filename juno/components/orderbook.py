from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import Fees, Fill, Fills, OrderType, Side, SymbolInfo
from juno.config import list_required_names
from juno.exchanges import Exchange
from juno.math import adjust_size
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import Barrier, unpack_symbol

_log = logging.getLogger(__name__)


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
                               symbol_info: SymbolInfo, fees: Fees) -> Fills:
        result = Fills()
        asks = self._orderbooks[exchange][symbol]['asks']
        for aprice, asize in sorted(asks.items()):
            aquote = aprice * asize
            base_asset, quote_asset = unpack_symbol(symbol)
            if aquote >= quote:
                size = adjust_size(quote / aprice, symbol_info.min_size, symbol_info.max_size,
                                   symbol_info.size_step)
                if size != Decimal(0):
                    fee = aprice * size * fees.taker
                    result.append(Fill(price=aprice, size=size, fee=fee, fee_asset=base_asset))
                break
            else:
                assert asize != Decimal(0)
                fee = aprice * asize * fees.taker
                result.append(Fill(price=aprice, size=asize, fee=fee, fee_asset=base_asset))
                quote -= aquote
        return result

    def find_market_order_bids(self, exchange: str, symbol: str, base: Decimal,
                               symbol_info: SymbolInfo, fees: Fees) -> Fills:
        result = Fills()
        asks = self._orderbooks[exchange][symbol]['bids']
        for bprice, bsize in sorted(asks.items(), reverse=True):
            base_asset, quote_asset = unpack_symbol(symbol)
            if bsize >= base:
                size = adjust_size(base, symbol_info.min_size, symbol_info.max_size,
                                   symbol_info.size_step)
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

    async def place_order(self, exchange: str, symbol: str, side: Side, size: Decimal,
                          test: bool = True) -> Any:
        return await self._exchanges[exchange].place_order(
            symbol=symbol,
            side=side,
            type_=OrderType.MARKET,
            size=size,
            test=True)

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
