import asyncio
import logging
import operator
import uuid
from decimal import Decimal
from typing import AsyncIterable, List

from juno import (
    CancelOrderStatus, Fill, Fills, InsufficientBalance, OrderResult, OrderUpdate, OrderStatus,
    OrderType, Side, TimeInForce
)
from juno.asyncio import cancel, cancelable
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange
from juno.math import round_half_up

from .broker import Broker

_log = logging.getLogger(__name__)


class Limit(Broker):
    def __init__(
        self, informant: Informant, orderbook: Orderbook, exchanges: List[Exchange]
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        assert not test
        _log.info(f'filling {quote} worth of quote with limit orders at spread')
        res = await self._fill(exchange, symbol, Side.BUY, quote)

        # Validate fee expectation.
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        expected_fee = round_half_up(res.fills.total_size * fees.maker, filters.base_precision)
        if res.fills.total_fee != expected_fee:
            # TODO: Python 3.8 debug strings.
            _log.warning(f'fee {res.fills.total_fee} != expected fee {expected_fee} ('
                         f'size={res.fills.total_size}, fee_pct={fees.maker}, '
                         f'base_precision={filters.base_precision})')

        return res

    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        assert not test
        _log.info(f'filling {base} worth of base with limit orders at spread')
        res = await self._fill(exchange, symbol, Side.SELL, base)

        # Validate fee expectation.
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        expected_fee = round_half_up(res.fills.total_quote * fees.maker, filters.quote_precision)
        if res.fills.total_fee != expected_fee:
            _log.warning(f'fee {res.fills.total_fee} != expected fee {expected_fee} ('
                         f'quote={res.fills.total_quote}, fee_pct={fees.maker}, '
                         f'quote_precision={filters.quote_precision})')

        return res

    async def _fill(
        self, exchange: str, symbol: str, side: Side, available: Decimal
    ) -> OrderResult:
        client_id = str(uuid.uuid4())

        async with self._exchanges[exchange].connect_stream_orders() as stream:
            # Keeps a limit order at spread.
            keep_limit_order_best_task = asyncio.create_task(
                cancelable(
                    self._keep_limit_order_best(
                        exchange=exchange,
                        symbol=symbol,
                        client_id=client_id,
                        side=side,
                        available=available
                    )
                )
            )

            # Listens for fill events for an existing order.
            track_fills_task = asyncio.create_task(
                cancelable(self._track_fills(client_id=client_id, symbol=symbol, stream=stream,
                           keep_limit_order_best_task=keep_limit_order_best_task))
            )

            await asyncio.gather(keep_limit_order_best_task, track_fills_task)

        return OrderResult(status=OrderStatus.FILLED, fills=track_fills_task.result())

    async def _keep_limit_order_best(
        self, exchange: str, symbol: str, client_id: str, side: Side, available: Decimal
    ) -> None:
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
                    'is optimal price?'
                )

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
                _log.info(
                    f'cancelling previous limit order {client_id} at price '
                    f'{last_order_price}'
                )
                cancel_res = await self._exchanges[exchange].cancel_order(
                    symbol=symbol, client_id=client_id
                )
                if cancel_res.status is CancelOrderStatus.REJECTED:
                    _log.warning(f'failed to cancel order {client_id}; probably got filled')
                    break

            # No need to round price as we take it from existing orders.
            size = available / price if side is Side.BUY else available
            size = filters.size.round_down(size)

            if size == 0:
                _log.info('skipping order placement; size 0')
                raise InsufficientBalance()

            if not filters.min_notional.valid(price=price, size=size):
                # TODO: Implement. raise InsuficientBalance error.
                _log.info(f'min notional not satisfied: {price} * {size} != '
                          f'{filters.min_notional.min_notional}')
                raise InsufficientBalance()

            _log.info(f'placing limit order at price {price} for size {size}')
            res = await self._exchanges[exchange].place_order(
                symbol=symbol,
                side=side,
                type_=OrderType.LIMIT,
                price=price,
                size=size,
                time_in_force=TimeInForce.GTC,
                client_id=client_id,
                test=False
            )

            if res.status is OrderStatus.FILLED:
                _log.info(f'new limit order {client_id} immediately filled {res.fills}')
                break
            last_order_price = price

    async def _track_fills(self, client_id: str, symbol: str, stream: AsyncIterable[OrderUpdate],
                           keep_limit_order_best_task: asyncio.Task):
        fills = Fills()  # Fills from aggregated trades.

        async for order in stream:
            if order.client_id != client_id:
                continue
            if order.symbol != symbol:
                _log.warning(f'order {client_id} symbol {order.symbol} != {symbol} ')
                continue
            if order.status is OrderStatus.NEW:
                _log.debug(f'received new confirmation for order {client_id}')
                continue
            if order.status not in [
                OrderStatus.CANCELED, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED
            ]:
                _log.error(f'unexpected order update with status {order.status}')
                continue

            if order.status in [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED]:
                assert order.fee_asset
                fills.append(
                    Fill(
                        price=order.price,
                        size=order.size,
                        fee=order.fee,
                        fee_asset=order.fee_asset
                    )
                )
                if order.status is OrderStatus.FILLED:
                    _log.info(f'existing order {client_id} filled')
                    break
                else:  # PARTIALLY_FILLED
                    _log.info(f'existing order {client_id} partially filled')
            else:  # CANCELED
                _log.info(f'existing order {client_id} canceled')

        await cancel(keep_limit_order_best_task)
        return fills
