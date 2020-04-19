import asyncio
import logging
import operator
import uuid
from decimal import Decimal
from typing import AsyncIterable, Callable, List

from juno import (
    Fill, OrderException, OrderResult, OrderStatus, OrderType, OrderUpdate, Side, TimeInForce
)
from juno.asyncio import Event, cancel
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange

from .broker import Broker

_log = logging.getLogger(__name__)


class _Context:
    def __init__(self, available: Decimal, use_quote: bool) -> None:
        self.available = available
        self.use_quote = use_quote
        self.new_event: Event[None] = Event(autoclear=True)
        self.cancelled_event: Event[None] = Event(autoclear=True)


class Limit(Broker):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        exchanges: List[Exchange],
        get_client_id: Callable[[], str] = lambda: str(uuid.uuid4())
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_client_id = get_client_id

    async def buy(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        _log.info(f'buying {size} worth of base asset with limit orders at spread')
        return await self._buy(exchange, symbol, margin, _Context(available=size, use_quote=False))

    async def buy_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        _log.info(f'buying {quote} worth of quote asset with limit orders at spread')
        return await self._buy(exchange, symbol, margin, _Context(available=quote, use_quote=True))

    async def _buy(self, exchange: str, symbol: str, margin: bool, ctx: _Context) -> OrderResult:
        res = await self._fill(exchange, symbol, Side.BUY, margin, ctx)

        # Validate fee expectation.
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        expected_fee = Fill.expected_base_fee(res.fills, fees.maker, filters.base_precision)
        if Fill.total_fee(res.fills) != expected_fee:
            _log.warning(
                f'total_fee={Fill.total_fee(res.fills)} != {expected_fee=} '
                f'(total_size={Fill.total_size(res.fills)}, {fees.maker=}, '
                f'{filters.base_precision=})'
            )

        return res

    async def sell(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        _log.info(f'selling {size} worth of base asset with limit orders at spread')
        ctx = _Context(available=size, use_quote=False)
        res = await self._fill(exchange, symbol, Side.SELL, margin, ctx)

        # Validate fee expectation.
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        expected_fee = Fill.expected_quote_fee(res.fills, fees.maker, filters.quote_precision)
        if Fill.total_fee(res.fills) != expected_fee:
            _log.warning(
                f'total_fee={Fill.total_fee(res.fills)} != {expected_fee=} '
                f'(total_quote={Fill.total_quote(res.fills)}, {fees.maker=}, '
                f'{filters.quote_precision=})'
            )

        return res

    async def _fill(
        self, exchange: str, symbol: str, side: Side, margin: bool, ctx: _Context
    ) -> OrderResult:
        client_id = self._get_client_id()

        async with self._exchanges[exchange].connect_stream_orders(margin=margin) as stream:
            # Keeps a limit order at spread.
            keep_limit_order_best_task = asyncio.create_task(
                self._keep_limit_order_best(
                    exchange=exchange,
                    symbol=symbol,
                    client_id=client_id,
                    side=side,
                    margin=margin,
                    ctx=ctx,
                )
            )

            # Listens for fill events for an existing order.
            track_fills_task = asyncio.create_task(
                self._track_fills(
                    client_id=client_id,
                    symbol=symbol,
                    stream=stream,
                    side=side,
                    ctx=ctx,
                )
            )

        try:
            await asyncio.gather(keep_limit_order_best_task, track_fills_task)
        except OrderException:
            await cancel(keep_limit_order_best_task, track_fills_task)
            raise
        except _Filled as exc:
            fills = exc.fills
            await cancel(keep_limit_order_best_task)

        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def _keep_limit_order_best(
        self, exchange: str, symbol: str, client_id: str, side: Side, margin: bool, ctx: _Context
    ) -> None:
        orderbook_updated = self._orderbook.get_updated_event(exchange, symbol)
        _, filters = self._informant.get_fees_filters(exchange, symbol)
        last_order_price = Decimal('0.0') if side is Side.BUY else Decimal('Inf')
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
                    f'no existing {"bids" if side is Side.BUY else "asks"} in orderbook! what is '
                    'optimal price?'
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
                    f'cancelling previous limit order {client_id} at price {last_order_price}'
                )
                try:
                    await self._exchanges[exchange].cancel_order(
                        symbol=symbol, client_id=client_id, margin=margin
                    )
                except OrderException as exc:
                    _log.warning(f'failed to cancel order {client_id}; probably got filled; {exc}')
                    break
                _log.info(f'waiting for order {client_id} to be cancelled')
                await ctx.cancelled_event.wait()

            # No need to round price as we take it from existing orders.
            size = ctx.available / price if ctx.use_quote else ctx.available
            size = filters.size.round_down(size)

            filters.size.validate(size)
            filters.min_notional.validate_limit(price=price, size=size)

            _log.info(f'placing limit order at price {price} for size {size}')
            await self._exchanges[exchange].place_order(
                symbol=symbol,
                side=side,
                type_=OrderType.LIMIT,
                price=price,
                size=size,
                time_in_force=TimeInForce.GTC,
                client_id=client_id,
                test=False,
                margin=margin,
            )
            await ctx.new_event.wait()

            last_order_price = price

    async def _track_fills(
        self, client_id: str, symbol: str, stream: AsyncIterable[OrderUpdate],
        side: Side, ctx: _Context
    ) -> None:
        fills = []  # Fills from aggregated trades.
        async for order in stream:
            if order.client_id != client_id:
                _log.debug(f'skipping order tracking; {order.client_id=} != {client_id=}')
                continue
            if order.symbol != symbol:
                _log.warning(f'order {client_id} symbol {order.symbol=} != {symbol=}')
                continue
            if order.status is OrderStatus.NEW:
                _log.info(f'received new confirmation for order {client_id}')
                deduct = order.size * order.price if ctx.use_quote else order.size
                ctx.available -= deduct
                ctx.new_event.set()
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
                        size=order.filled_size,
                        quote=order.filled_quote,
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
                add_back_size = order.size - order.cumulative_filled_size
                add_back = add_back_size * order.price if ctx.use_quote else add_back_size
                ctx.available += add_back
                ctx.cancelled_event.set()

        raise _Filled(fills)


class _Filled(Exception):
    def __init__(self, fills: List[Fill]) -> None:
        self.fills = fills
