from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import Fees, Fill, Fills, OrderResult, OrderStatus, OrderType, Side, TimeInForce
from juno.config import list_required_names
from juno.exchanges import Exchange
from juno.filters import Filters
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import Barrier, unpack_symbol

_log = logging.getLogger(__name__)


class _Orderbook(Dict[str, Dict[Decimal, Decimal]]):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.updated = asyncio.Event()
        self.snapshot_received = False


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
                status=OrderStatus.NOT_PLACED,
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

        fills = res.fills
        to_fill -= res.fills.total_size

        if to_fill == 0:
            assert res.status == OrderStatus.FILLED
        else:
            assert res.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
            # Re-adjust order if someone surpasses us in orderbook.
            adj_task = asyncio.create_task(self._readjust_order_best(client_id, exchange, symbol))
            # Listen to order updates until we fill.
            add_fills = await self._wait_order_fills(to_fill, client_id, exchange, adj_task)
            fills.extend(add_fills)

        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def _wait_order_fills(self, to_fill: Decimal, client_id: str, exchange: str,
                                adj_task: asyncio.Task[None]) -> List[Fill]:
        fills = []
        # try:
        async for order in self._exchanges[exchange].stream_orders():
            if order['order_client_id'] != client_id:
                continue
            if order['status'] != 'TRADE':
                # TODO: temp logging
                _log.critical(f'order update with status {order["status"]}')
                continue

            to_fill -= order['fill_size']
            fills.append(Fill(
                price=order['fill_price'],
                size=order['fill_size'],
                fee=order['fee'],
                fee_asset=order['fee_asset']))
            if to_fill == 0:
                assert order['order_status'] == OrderStatus.FILLED
                break
        # Cancels re-adjustment of the order task.
        adj_task.cancel()
        # except asyncio.CancelledError:
        #     _log.info(f'order {client_id} wait for fill task cancelled')
        # except Exception:
        #     _log.exception(f'unhandled exception in order {client_id} wait for fill task')
        #     raise
        return fills

    async def _readjust_order_best(self, client_id: str, exchange: str, symbol: str) -> None:
        try:
            orderbook = self._orderbooks[exchange][symbol]
            while True:
                await orderbook.updated.wait()
                orderbook.updated.clear()
                # TODO
        except asyncio.CancelledError:
            _log.info(f'order {client_id} re-adjustment task cancelled')
        except Exception:
            _log.exception(f'unhandled exception in order {client_id} re-adjustment task')
            raise

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
        async for val in self._exchanges[exchange].stream_depth(symbol):
            if val['type'] == 'snapshot':
                orderbook['bids'] = {k: v for k, v in val['bids']}
                orderbook['asks'] = {k: v for k, v in val['asks']}
                orderbook.snapshot_received = True
                self._initial_orderbook_fetched.release()
            elif val['type'] == 'update':
                assert orderbook.snapshot_received
                _update_orderbook_side(orderbook['bids'], val['bids'])
                _update_orderbook_side(orderbook['asks'], val['asks'])
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
