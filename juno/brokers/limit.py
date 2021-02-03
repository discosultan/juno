import asyncio
import logging
import operator
import uuid
from decimal import Decimal
from typing import AsyncIterable, Callable, Optional

from juno import Fill, OrderException, OrderResult, OrderStatus, OrderType, OrderUpdate, Side
from juno.asyncio import Event, cancel
from juno.components import Informant, Orderbook, User
from juno.utils import unpack_symbol

from .broker import Broker

_log = logging.getLogger(__name__)


class _Context:
    def __init__(self, available: Decimal, use_quote: bool, client_id: str) -> None:
        self.original = available
        self.available = available
        self.use_quote = use_quote
        self.client_id = client_id
        self.new_event: Event[None] = Event(autoclear=True)
        self.cancelled_event: Event[list[Fill]] = Event(autoclear=True)
        self.fills: list[Fill] = []  # Fills from aggregated trades.
        self.time: int = -1
        self.active_order: Optional[_ActiveOrder] = None


class _ActiveOrder:
    def __init__(self, price: Decimal, size: Decimal) -> None:
        self.price = price
        self.size = size


class _FilledFromTrack(Exception):
    pass


class _FilledFromKeepAtBest(Exception):
    pass


class Limit(Broker):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        get_client_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        cancel_order_on_error: bool = True,
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._user = user
        self._get_client_id = get_client_id
        self._cancel_order_on_error = cancel_order_on_error

    async def buy(
        self,
        exchange: str,
        account: str,
        symbol: str,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        ensure_size: bool = False,
    ) -> OrderResult:
        assert not test
        Broker.validate_funds(size, quote)

        base_asset, quote_asset = unpack_symbol(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            _log.info(
                f'buying {size} (ensure size: {ensure_size}) {base_asset} with limit orders at '
                f'spread ({account} account)'
            )
            if ensure_size:
                size = filters.with_fee(size, fees.maker)
        elif quote is not None:
            _log.info(
                f'buying {quote} {quote_asset} worth of {base_asset} with limit orders at spread '
                f'({account} account)'
            )
        else:
            raise NotImplementedError()

        res = await self._fill(
            exchange, account, symbol, Side.BUY, ensure_size, size=size, quote=quote
        )

        # Validate fee and quote expectation.
        expected_fee = Fill.expected_base_fee(res.fills, fees.maker, filters.base_precision)
        expected_quote = Fill.expected_quote(res.fills, filters.quote_precision)
        if Fill.total_fee(res.fills) != expected_fee:
            _log.warning(
                f'total_fee={Fill.total_fee(res.fills)} != {expected_fee=} '
                f'(total_size={Fill.total_size(res.fills)}, {fees.maker=}, '
                f'{filters.base_precision=})'
            )
        if Fill.total_quote(res.fills) != expected_quote:
            _log.warning(f'total_quote={Fill.total_quote(res.fills)} != {expected_quote=}')

        return res

    async def sell(
        self,
        exchange: str,
        account: str,
        symbol: str,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
    ) -> OrderResult:
        assert not test
        assert size  # TODO: support by quote
        Broker.validate_funds(size, quote)

        base_asset, _ = unpack_symbol(symbol)
        _log.info(
            f'selling {size} {base_asset} with limit orders at spread ({account} account)'
        )
        res = await self._fill(exchange, account, symbol, Side.SELL, False, size=size)

        # Validate fee and quote expectation.
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        expected_fee = Fill.expected_quote_fee(res.fills, fees.maker, filters.quote_precision)
        expected_quote = Fill.expected_quote(res.fills, filters.quote_precision)
        if Fill.total_fee(res.fills) != expected_fee:
            _log.warning(
                f'total_fee={Fill.total_fee(res.fills)} != {expected_fee=} '
                f'(total_quote={Fill.total_quote(res.fills)}, {fees.maker=}, '
                f'{filters.quote_precision=})'
            )
        if Fill.total_quote(res.fills) != expected_quote:
            _log.warning(f'total_quote={Fill.total_quote(res.fills)} != {expected_quote=}')

        return res

    async def _fill(
        self, exchange: str, account: str, symbol: str, side: Side, ensure_size: bool,
        size: Optional[Decimal] = None, quote: Optional[Decimal] = None
    ) -> OrderResult:
        client_id = self._get_client_id()
        if size is not None:
            if size == 0:
                raise ValueError('Size specified but 0')
            ctx = _Context(available=size, use_quote=False, client_id=client_id)
        elif quote is not None:
            if quote == 0:
                raise ValueError('Quote specified but 0')
            ctx = _Context(available=quote, use_quote=True, client_id=client_id)
        else:
            raise ValueError('Neither size nor quote specified')

        async with self._user.connect_stream_orders(
            exchange=exchange, account=account, symbol=symbol
        ) as stream:
            # Listens for fill events for an existing Order.
            track_fills_task = asyncio.create_task(
                self._track_fills(
                    symbol=symbol,
                    stream=stream,
                    side=side,
                    ctx=ctx,
                )
            )

            # Keeps a limit order at spread.
            keep_limit_order_best_task = asyncio.create_task(
                self._keep_limit_order_best(
                    exchange=exchange,
                    account=account,
                    symbol=symbol,
                    side=side,
                    ensure_size=ensure_size,
                    ctx=ctx,
                )
            )

            try:
                await asyncio.gather(keep_limit_order_best_task, track_fills_task)
            except OrderException:
                await cancel(keep_limit_order_best_task, track_fills_task)
                raise
            except _FilledFromKeepAtBest:
                try:
                    await cancel(track_fills_task)
                except _FilledFromTrack:
                    pass
            except _FilledFromTrack:
                try:
                    await cancel(keep_limit_order_best_task)
                except _FilledFromKeepAtBest:
                    pass
            finally:
                if self._cancel_order_on_error and ctx.active_order:
                    # Cancel active order.
                    _log.info(
                        f'cancelling active {symbol} {side.name} order {ctx.client_id} at price '
                        f'{ctx.active_order.price}'
                    )
                    await self._cancel_order(
                        exchange=exchange, account=account, symbol=symbol, client_id=ctx.client_id
                    )

        assert ctx.time >= 0
        return OrderResult(time=ctx.time, status=OrderStatus.FILLED, fills=ctx.fills)

    async def _keep_limit_order_best(
        self, exchange: str, account: str, symbol: str, side: Side, ensure_size: bool,
        ctx: _Context
    ) -> None:
        _, filters = self._informant.get_fees_filters(exchange, symbol)
        is_first = True
        async with self._orderbook.sync(exchange, symbol) as orderbook:
            while True:
                if is_first:
                    is_first = False
                else:
                    await orderbook.updated.wait()

                asks = orderbook.list_asks()
                bids = orderbook.list_bids()
                ob_side = bids if side is Side.BUY else asks
                ob_other_side = asks if side is Side.BUY else bids
                op_step = operator.add if side is Side.BUY else operator.sub
                op_last_price_cmp = operator.le if side is Side.BUY else operator.ge

                if len(ob_side) == 0:
                    raise NotImplementedError(
                        f'no existing {symbol} {"bids" if side is Side.BUY else "asks"} in '
                        'orderbook! what is optimal price?'
                    )

                if len(ob_other_side) == 0:
                    price = op_step(ob_side[0][0], filters.price.step)
                else:
                    spread = abs(ob_other_side[0][0] - ob_side[0][0])
                    if spread == filters.price.step:
                        price = ob_side[0][0]
                    else:
                        price = op_step(ob_side[0][0], filters.price.step)

                # If we have an order in the orderbook.
                if ctx.active_order:
                    if op_last_price_cmp(price, ctx.active_order.price):
                        continue

                    # Cancel prev order.
                    _log.info(
                        f'cancelling previous {symbol} {side.name} order {ctx.client_id} at price '
                        f'{ctx.active_order.price}'
                    )
                    if not await self._cancel_order(
                        exchange=exchange, account=account, symbol=symbol, client_id=ctx.client_id
                    ):
                        break
                    _log.info(
                        f'waiting for {symbol} {side.name} order {ctx.client_id} to be cancelled'
                    )
                    fills_since_last_order = await ctx.cancelled_event.wait()
                    filled_size_since_last_order = Fill.total_size(fills_since_last_order)
                    add_back_size = ctx.active_order.size - filled_size_since_last_order
                    add_back = (
                        add_back_size * ctx.active_order.price if ctx.use_quote else add_back_size
                    )
                    _log.info(
                        f'last {symbol} {side.name} order size {ctx.active_order.size} but filled '
                        f'{filled_size_since_last_order}; {add_back_size} still to be filled'
                    )
                    ctx.available += add_back
                    # Use a new client ID for new order.
                    ctx.client_id = self._get_client_id()
                    ctx.active_order = None

                # No need to round price as we take it from existing orders.
                size = ctx.available / price if ctx.use_quote else ctx.available
                size = filters.size.round_down(size)

                _log.info(f'validating {symbol} {side.name} order price and size')
                if len(ctx.fills) == 0:
                    # We only want to raise an exception if the filters fail while we haven't had
                    # any fills yet.
                    filters.size.validate(size)
                    filters.min_notional.validate_limit(price=price, size=size)
                else:
                    try:
                        filters.size.validate(size)
                        filters.min_notional.validate_limit(price=price, size=size)
                    except OrderException as e:
                        _log.info(f'{symbol} {side.name} price / size no longer valid: {e}')
                        if ensure_size and Fill.total_size(ctx.fills) < ctx.original:
                            size = filters.min_size(price)
                            _log.info(f'increased size to {size}')
                        else:
                            raise _FilledFromKeepAtBest()

                _log.info(f'placing {symbol} {side.name} order at price {price} for size {size}')
                try:
                    await self._user.place_order(
                        exchange=exchange,
                        account=account,
                        symbol=symbol,
                        side=side,
                        type_=OrderType.LIMIT_MAKER,
                        price=price,
                        size=size,
                        client_id=ctx.client_id,
                    )
                except OrderException:
                    # Order would immediately match and take. Retry.
                    continue

                await ctx.new_event.wait()
                deduct = price * size if ctx.use_quote else size
                ctx.available -= deduct
                ctx.active_order = _ActiveOrder(price=price, size=size)

    async def _track_fills(
        self, symbol: str, stream: AsyncIterable[OrderUpdate.Any], side: Side, ctx: _Context
    ) -> None:
        fills_since_last_order: list[Fill] = []
        async for order in stream:
            if order.client_id != ctx.client_id:
                _log.debug(
                    f'skipping {symbol} {side.name} order tracking; {order.client_id=} != '
                    f'{ctx.client_id=}'
                )
                continue

            if isinstance(order, OrderUpdate.New):
                _log.info(f'new {symbol} {side.name} order {ctx.client_id} confirmed')
                fills_since_last_order.clear()
                ctx.new_event.set()
            elif isinstance(order, OrderUpdate.Match):
                _log.info(f'existing {symbol} {side.name} order {ctx.client_id} matched')
                fills_since_last_order.append(order.fill)
            elif isinstance(order, OrderUpdate.Cancelled):
                _log.info(f'existing {symbol} {side.name} order {ctx.client_id} cancelled')
                ctx.fills.extend(fills_since_last_order)
                ctx.time = order.time
                ctx.cancelled_event.set(fills_since_last_order)
            elif isinstance(order, OrderUpdate.Done):
                _log.info(f'existing {symbol} {side.name} order {ctx.client_id} filled')
                ctx.fills.extend(fills_since_last_order)
                ctx.time = order.time
                ctx.active_order = None
                raise _FilledFromTrack()
            else:
                raise NotImplementedError(order)

    async def _cancel_order(
        self, exchange: str, account: str, symbol: str, client_id: str
    ) -> bool:
        try:
            await self._user.cancel_order(
                exchange=exchange,
                symbol=symbol,
                client_id=client_id,
                account=account,
            )
            return True
        except OrderException as exc:
            _log.warning(
                f'failed to cancel {symbol} order {client_id}; probably got filled; {exc}'
            )
            return False
