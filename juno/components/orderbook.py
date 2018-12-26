import asyncio
from collections import defaultdict
from itertools import product
import logging

from juno.utils import Barrier


_log = logging.getLogger(__name__)


class Orderbook:

    def __init__(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._symbols = config['symbols']
        self._orderbooks_product = list(product(self._exchanges.keys(), self._symbols))
        self._initial_orderbook_fetched = Barrier(len(self._orderbooks_product))

        self._orderbooks = defaultdict(lambda: defaultdict(dict))

    async def __aenter__(self):
        self._sync_task = asyncio.get_running_loop().create_task(self._sync_orderbooks())
        await self._initial_orderbook_fetched.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sync_task.cancel()

    async def _sync_orderbooks(self):
        try:
            await asyncio.gather(
                *(self._sync_orderbook(e, s) for e, s in self._orderbooks_product))
        except asyncio.CancelledError:
            _log.info('orderbook sync task cancelled')

    async def _sync_orderbook(self, exchange, symbol):
        async for val in self._exchanges[exchange].stream_depth(symbol):
            if val['type'] == 'snapshot':
                orderbook = {
                    'bids': {k: v for k, v in val['bids']},
                    'asks': {k: v for k, v in val['asks']}
                }
                self._orderbooks[exchange][symbol] = orderbook
                self._initial_orderbook_fetched.release()
            elif val['type'] == 'update':
                _update_orderbook_side(orderbook['bids'], val['bids'])
                _update_orderbook_side(orderbook['asks'], val['asks'])
            else:
                raise NotImplementedError()


def _update_orderbook_side(orderbook_side, values):
    for price, size in values:
        if size == 0.0 and price in orderbook_side:
            del orderbook_side[price]
        else:
            orderbook_side[price] = size
