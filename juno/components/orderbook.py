from __future__ import annotations

import asyncio
import logging
import operator
import uuid
from collections import defaultdict
from decimal import Decimal
from itertools import product
from typing import Any, Dict, List, Tuple

from juno import (CancelOrderStatus, DepthUpdateType, Fees, Fill, Fills, OrderResult, OrderStatus,
                  OrderType, Side, TimeInForce)
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
            _log.info('skipping market order placement; size zero')
            return OrderResult.not_placed()

        _log.info(f'placing market {side} order of size {fills.total_size}')
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
                                  fees: Fees, filters: Filters) -> OrderResult:
        _log.info(f'filling {quote} worth of quote with limit orders at spread')
        res = await self._limit_at_spread(exchange, symbol, Side.BUY, quote, filters)
        # TODO: DEBUG. Doesn't exactly match as exchange performs rounding.
        _log.critical(f'total fee {res.fills.total_fee} == {res.fills.total_size} * {fees.maker}')
        return res

    async def sell_limit_at_spread(self, exchange: str, symbol: str, base: Decimal,
                                   fees: Fees, filters: Filters) -> OrderResult:
        _log.info(f'filling {base} worth of base with limit orders at spread')
        res = await self._limit_at_spread(exchange, symbol, Side.SELL, base, filters)
        _log.critical(f'total fee {res.fills.total_fee} == {res.fills.total_quote} * {fees.maker}')
        return res

    async def _limit_at_spread(self, exchange: str, symbol: str, side: Side, available: Decimal,
                               filters: Filters) -> OrderResult:
        client_id = str(uuid.uuid4())
        fills = Fills()  # Fills from aggregated trades.

        async with self._exchanges[exchange].stream_orders() as order_stream:
            # Keeps a limit order at spread.
            keep_limit_order_best_task = asyncio.create_task(
                self._keep_limit_order_best(
                    exchange=exchange,
                    symbol=symbol,
                    client_id=client_id,
                    side=side,
                    available=available,
                    filters=filters))

            # Listens for fill events for an existing order.
            async for order in order_stream:
                if order.client_id != client_id:
                    continue
                if order.symbol != symbol:
                    continue
                if order.status not in [OrderStatus.CANCELED, OrderStatus.FILLED]:
                    # TODO: temp logging
                    _log.critical(f'order update with status {order.status}')
                    continue

                if order.status is OrderStatus.FILLED:
                    _log.info(f'existing order {client_id} filled')
                    assert order.fee_asset
                    fills.append(Fill(
                        price=order.price,
                        size=order.size,
                        fee=order.fee,
                        fee_asset=order.fee_asset))
                    break
                else:  # CANCELED
                    _log.info(f'existing order {client_id} canceled')
                    if order.cumulative_filled_size > 0:
                        assert order.fee_asset
                        fills.append(Fill(
                            price=order.price,
                            size=order.cumulative_filled_size,
                            fee=order.fee,
                            fee_asset=order.fee_asset))

            keep_limit_order_best_task.cancel()
            await keep_limit_order_best_task

        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def _keep_limit_order_best(self, exchange: str, symbol: str, client_id: str, side: Side,
                                     available: Decimal, filters: Filters) -> None:
        try:
            orderbook = self._orderbooks[exchange][symbol]
            last_order_price = Decimal(0) if side is Side.BUY else Decimal('Inf')
            while True:
                await orderbook.updated.wait()
                orderbook.updated.clear()

                asks = self.list_asks(exchange, symbol)
                bids = self.list_bids(exchange, symbol)
                ob_side = bids if side is Side.BUY else asks
                ob_other_side = asks if side is Side.BUY else bids
                op_step = operator.add if side is Side.BUY else operator.sub
                op_last_price_cmp = operator.le if side is Side.BUY else operator.ge

                if len(ob_side) == 0:
                    raise NotImplementedError(
                        f'no existing {"bids" if side is Side.BUY else "asks"} in orderbook! what '
                        'is optimal price?')

                if len(ob_other_side) == 0:
                    price = op_step(ob_side[0][0], filters.price.step)
                else:
                    spread = abs(ob_other_side[0][0] - ob_side[0][0])
                    if spread == filters.price.step:
                        price = ob_side[0][0]
                    else:
                        price = op_step(ob_side[0][0], filters.price.step)

                if op_last_price_cmp(price, last_order_price):
                    continue

                if last_order_price not in [0, Decimal('Inf')]:
                    # Cancel prev order.
                    _log.info(f'cancelling previous limit order {client_id} at price '
                              f'{last_order_price}')
                    cancel_res = await self._exchanges[exchange].cancel_order(
                        symbol=symbol, client_id=client_id)
                    if cancel_res.status is CancelOrderStatus.REJECTED:
                        _log.warning(f'failed to cancel order {client_id}; probably got filled')
                        break

                # No need to round price as we take it from existing orders.
                size = available / price if side is Side.BUY else available
                size = filters.size.round_down(size)

                if size == 0:
                    raise NotImplementedError('size 0')

                if not filters.min_notional.valid(price=price, size=size):
                    raise NotImplementedError(
                        'min notional not valid: '
                        f'{price} * {size} != {filters.min_notional.min_notional}')

                _log.info(f'placing limit order at price {price} for size {size}')
                res = await self._exchanges[exchange].place_order(
                    symbol=symbol,
                    side=side,
                    type_=OrderType.LIMIT,
                    price=price,
                    size=size,
                    time_in_force=TimeInForce.GTC,
                    client_id=client_id,
                    test=False)

                if res.status is OrderStatus.FILLED:
                    _log.info(f'new limit order {client_id} immediately filled {res.fills}')
                    break
                last_order_price = price
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
