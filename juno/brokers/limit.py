import asyncio
import logging
import operator
import uuid
from decimal import Decimal
from typing import List

from juno import (CancelOrderStatus, Fill, Fills, OrderResult, OrderStatus, OrderType, Side,
                  TimeInForce)
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange

_log = logging.getLogger(__name__)


class Limit:

    def __init__(self, informant: Informant, orderbook: Orderbook, exchanges: List[Exchange]
                 ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        assert not test
        _log.info(f'filling {quote} worth of quote with limit orders at spread')
        res = await self._fill(exchange, symbol, Side.BUY, quote)
        # TODO: DEBUG. Doesn't exactly match as exchange performs rounding.
        fees = self._informant.get_fees(exchange, symbol)
        _log.critical(f'total fee {res.fills.total_fee} == {res.fills.total_size} * {fees.maker}')
        return res

    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        assert not test
        _log.info(f'filling {base} worth of base with limit orders at spread')
        res = await self._fill(exchange, symbol, Side.SELL, base)
        fees = self._informant.get_fees(exchange, symbol)
        _log.critical(f'total fee {res.fills.total_fee} == {res.fills.total_quote} * {fees.maker}')
        return res

    async def _fill(self, exchange: str, symbol: str, side: Side, available: Decimal
                    ) -> OrderResult:
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
                    available=available))

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
                                     available: Decimal) -> None:
        try:
            orderbook_updated = self._orderbook.get_updated_event(exchange, symbol)
            filters = self._informant.get_filters(exchange, symbol)
            last_order_price = Decimal(0) if side is Side.BUY else Decimal('Inf')
            while True:
                await orderbook_updated.wait()

                asks = self._orderbook.list_asks(exchange, symbol)
                bids = self._orderbook.list_bids(exchange, symbol)
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
