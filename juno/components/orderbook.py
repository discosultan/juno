import asyncio
from collections import defaultdict
from decimal import Decimal
from itertools import product
import logging
from typing import Any, Dict

from juno.math import floor_multiple
from juno.utils import Barrier


_log = logging.getLogger(__name__)


class Orderbook:

    def __init__(self, services: dict, config: dict) -> None:
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._symbols = config['symbols']
        self._orderbooks_product = list(product(self._exchanges.keys(), self._symbols))

        self._orderbooks: Dict[str, Any] = defaultdict(lambda: defaultdict(dict))

    async def __aenter__(self):
        self._initial_orderbook_fetched = Barrier(len(self._orderbooks_product))
        self._sync_task = asyncio.create_task(self._sync_orderbooks())
        await self._initial_orderbook_fetched.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sync_task.cancel()
        await self._sync_task

    def find_market_order_buy_size(self, exchange: str, symbol: str, quote_balance: Decimal,
                                   size_step: Decimal) -> Decimal:
        orderbook = self._orderbooks[exchange][symbol]
        total_size = Decimal(0)
        available_quote = quote_balance
        for price, size in orderbook['asks'].items():
            cost = price * size
            if cost > available_quote:
                fill = floor_multiple(available_quote / price, size_step)
                available_quote -= fill * price
                total_size += fill
                break
            else:
                total_size += size
                available_quote -= cost
        # total_size = adjust_qty(size * percent, ap_info)
        return total_size

    def find_market_order_sell_size(self, exchange: str, symbol: str, base_balance: Decimal,
                                    size_step: Decimal) -> Decimal:
        orderbook = self._orderbooks[exchange][symbol]
        available_base = base_balance
        for _price, size in orderbook['bids'].items():
            if size > available_base:
                fill = floor_multiple(available_base, size_step)
                available_base -= fill
                break
            else:
                available_base -= size
        total_size = base_balance - available_base
        # total_size = adjust_qty(size * percent, ap_info)
        return total_size

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


def _update_orderbook_side(orderbook_side: Dict[str, Any], values: list) -> None:
    for price, size in values:
        if size == 0 and price in orderbook_side:
            del orderbook_side[price]
        else:
            orderbook_side[price] = size


# def adjust_size(size: Decimal, min_size: Decimal, max_size: Decimal, size_step: Decimal
#                 ) -> Decimal:
#     # Clamp within min and max.
#     size = max(min(size, max_size), min_size)
#     # Make sure to follow step size.
#     return round(size / size_step) * size_step
