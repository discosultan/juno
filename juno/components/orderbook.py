from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import Fees, Fill, Fills, OrderResult, OrderResultStatus, OrderType, Side, TimeInForce
from juno.config import list_required_names
from juno.exchanges import Exchange
from juno.filters import Filters
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

    def list_asks(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._orderbooks[exchange][symbol]['asks'].items())

    def list_bids(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._orderbooks[exchange][symbol]['bids'].items(), reverse=True)

    def find_market_order_asks(self, exchange: str, symbol: str, quote: Decimal, fees: Fees,
                               filters: Filters) -> Fills:
        result = Fills()
        for aprice, asize in self.list_asks(exchange, symbol):
            aquote = aprice * asize
            base_asset, quote_asset = unpack_symbol(symbol)
            if aquote >= quote:
                size = filters.size.round_down(quote / aprice)
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

    def find_market_order_bids(self, exchange: str, symbol: str, base: Decimal, fees: Fees,
                               filters: Filters) -> Fills:
        result = Fills()
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

    async def buy_market(self, exchange: str, symbol: str, quote: Decimal, fees: Fees,
                         filters: Filters, test: bool) -> OrderResult:
        # TODO: Add dep to Informant and fetch filters and fees from there?
        # Simplifies Orderbook usage but makes testing more difficult.
        fills = self.find_market_order_asks(exchange=exchange, symbol=symbol, quote=quote,
                                            fees=fees, filters=filters)
        return await self._fill_market(exchange=exchange, symbol=symbol, side=Side.BUY,
                                       fills=fills, test=test)

    async def sell_market(self, exchange: str, symbol: str, base: Decimal, fees: Fees,
                          filters: Filters, test: bool) -> OrderResult:
        fills = self.find_market_order_bids(exchange=exchange, symbol=symbol, base=base,
                                            fees=fees, filters=filters)
        return await self._fill_market(exchange=exchange, symbol=symbol, side=Side.SELL,
                                       fills=fills, test=test)

    async def _fill_market(self, exchange: str, symbol: str, side: Side, fills: Fills, test: bool
                           ) -> OrderResult:
        if fills.total_size == 0:
            return OrderResult.not_placed()

        res = await self._exchanges[exchange].place_order(
            symbol=symbol,
            side=side,
            type_=OrderType.MARKET,
            size=fills.total_size,
            test=test)
        if test:
            res = OrderResult(
                status=OrderResultStatus.NOT_PLACED,
                fills=fills)
        return res

    async def buy_limit_at_spread(self, exchange: str, symbol: str, quote: Decimal,
                                  filters: Filters) -> OrderResult:
        asks = self.list_asks(exchange, symbol)
        bids = self.list_bids(exchange, symbol)
        if len(bids) == 0:
            raise NotImplementedError('no existing bids in orderbook! what is optimal bid price?')
        if len(asks) == 0:
            price = bids[0][0] + filters.price.step
        else:
            spread = asks[0][0] - bids[0][0]
            if spread == filters.price.step:
                price = bids[0][0]
            else:
                price = bids[0][0] + filters.price.step
        # No need to adjust price as we take it from existing orders.
        size = filters.size.round_down(quote / price)

        if size == 0:
            return OrderResult.not_placed()

        client_id = str(uuid.uuid4())
        to_fill = size

        res = await self._exchanges[exchange].place_order(
            symbol=symbol,
            side=Side.BUY,
            type_=OrderType.LIMIT,
            price=price,
            size=size,
            time_in_force=TimeInForce.GTC,
            client_id=client_id,
            test=False)

        to_fill -= res.fills.total_size
        if to_fill > 0:
            async for order in self._exchanges[exchange].stream_orders():
                if order['client_id'] != client_id:
                    continue

        return None

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
        if size > 0:
            orderbook_side[price] = size
        elif price in orderbook_side:
            del orderbook_side[price]
        else:
            # Receiving an event that removes a price level that is not in the local orderbook can
            # happen and is normal for Binance, for example.
            pass
