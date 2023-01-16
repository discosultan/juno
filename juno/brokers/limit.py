import asyncio
import logging
import operator
from decimal import Decimal
from typing import AsyncIterable, Literal, NamedTuple, Optional

from juno import (
    Account,
    BadOrder,
    Fill,
    Filters,
    InsufficientFunds,
    OrderMissing,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    OrderWouldBeTaker,
    Side,
    Symbol,
    Symbol_,
)
from juno.asyncio import Event, cancel
from juno.common import CancelledReason
from juno.components import Informant, Orderbook, User
from juno.math import round_up

from .broker import Broker

_log = logging.getLogger(__name__)

_WS_EVENT_WAIT_TIMEOUT = 60


class _ActiveOrder(NamedTuple):
    client_id: str
    price: Decimal
    size: Decimal
    quote: Decimal


class _Context:
    def __init__(self, available: Decimal, use_quote: bool) -> None:
        # Can only be mutated by the order tracker task.
        self.original = available
        self.available = available
        self.use_quote = use_quote
        self.new_event: Event[None] = Event(autoclear=True)
        self.cancelled_event: Event[None] = Event(autoclear=True)
        self.done_event: Event[None] = Event(autoclear=False)
        self.fills: list[Fill] = []  # Fills from aggregated trades.
        self.fills_since_last_order: list[Fill] = []
        self.time: int = -1
        self.processing_order: Optional[_ActiveOrder] = None

        # Can be mutated by anyone.
        self.requested_order: Optional[_ActiveOrder] = None
        self.wait_orderbook_update: bool = False

    def get_add_back(self) -> Decimal:
        assert self.processing_order
        if self.use_quote:
            return self.processing_order.quote - Fill.total_quote(self.fills_since_last_order)
        else:
            return self.processing_order.size - Fill.total_size(self.fills_since_last_order)


class _FilledFromTrack(Exception):
    pass


class _FilledFromKeepAtBest(Exception):
    pass


class Limit(Broker):
    OrderPlacementStrategy = Literal["leading", "matching"]

    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        cancel_order_on_error: bool = True,
        # There's an inherent risk when using an exchange edit order functionality. For example,
        # we have placed order A. We are now editing order A to order B. During the edit request,
        # there's a partial match to order A. Order B still gets placed with the full size (without
        # taking the partial match into account). This way we can end in a situation where we spend
        # more than we intended.
        #
        # Separate cancel + place requests don't suffer from the above issue because we ack the
        # cancel request before placing the new request, knowing the price + size in advance.
        #
        # It's safe to use the edit order functionality as long as we trade with the full quote
        # asset amount. In this case, we simply receive InsufficientFunds error after a
        # partial match and can retry. As soon as we trade with a partial quote amount (as is the
        # case with the multi trader, for example), we may overspend.
        use_edit_order_if_possible: bool = True,
        order_placement_strategy: OrderPlacementStrategy = "matching",
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._user = user
        self._cancel_order_on_error = cancel_order_on_error
        self._use_edit_order_if_possible = use_edit_order_if_possible

        self._order_placement_strategy = order_placement_strategy
        if order_placement_strategy == "leading":
            self._find_order_placement_price = _leading_no_pullback
        elif order_placement_strategy == "matching":
            self._find_order_placement_price = _match_highest
        else:
            raise ValueError(f"unknown order placement strategy {order_placement_strategy}")

    async def buy(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        ensure_size: bool = False,
    ) -> OrderResult:
        assert not test
        Broker.validate_funds(size, quote)

        base_asset, quote_asset = Symbol_.assets(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            _log.info(
                f"buying {size} (ensure size: {ensure_size}) {base_asset} with limit orders at "
                f"spread ({account} account) following {self._order_placement_strategy} strategy; "
                f"using edit order if possible: {self._use_edit_order_if_possible}"
            )
            if ensure_size:
                size = filters.with_fee(size, fees.maker)
        elif quote is not None:
            _log.info(
                f"buying {quote} {quote_asset} worth of {base_asset} with limit orders at spread "
                f"({account} account) following {self._order_placement_strategy} strategy; using "
                f"edit order if possible: {self._use_edit_order_if_possible}"
            )
        else:
            raise NotImplementedError()

        res = await self._fill(
            exchange, account, symbol, Side.BUY, ensure_size, size=size, quote=quote
        )

        # Validate fee and quote expectation.
        expected_fee = Fill.expected_base_fee(res.fills, fees.maker, filters.base_precision)
        expected_quote = Fill.expected_quote(res.fills, filters.quote_precision)
        fee = Fill.total_fee(res.fills, base_asset)
        if fee != expected_fee:
            # TODO: Always warns when a different fee asset (such as BNB) is involved.
            # TODO: Buy fee is not always based on base asset. While that's the case of Binance,
            #       Kraken fees are usually based on quote asset regardless of buy or sell.
            _log.warning(
                f"total_fee={fee} != {expected_fee=} (total_size={Fill.total_size(res.fills)}, "
                f"{fees.maker=}, {filters.base_precision=})"
            )
        if Fill.total_quote(res.fills) != expected_quote:
            _log.warning(f"total_quote={Fill.total_quote(res.fills)} != {expected_quote=}")

        return res

    async def sell(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
    ) -> OrderResult:
        assert not test
        assert size is not None  # TODO: support by quote
        Broker.validate_funds(size, quote)

        base_asset, quote_asset = Symbol_.assets(symbol)
        _log.info(
            f"selling {size} {base_asset} with limit orders at spread ({account} account) "
            f"following {self._order_placement_strategy} strategy; using edit order if possible: "
            f"{self._use_edit_order_if_possible}"
        )
        res = await self._fill(exchange, account, symbol, Side.SELL, False, size=size)

        # Validate fee and quote expectation.
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        expected_fee = Fill.expected_quote_fee(res.fills, fees.maker, filters.quote_precision)
        expected_quote = Fill.expected_quote(res.fills, filters.quote_precision)
        fee = Fill.total_fee(res.fills, quote_asset)
        if fee != expected_fee:
            # TODO: Always warns when a different fee asset (such as BNB) is involved.
            _log.warning(
                f"total_fee={fee} != {expected_fee=} (total_quote={Fill.total_quote(res.fills)}, "
                f"{fees.maker=}, {filters.quote_precision=})"
            )
        if Fill.total_quote(res.fills) != expected_quote:
            _log.warning(f"total_quote={Fill.total_quote(res.fills)} != {expected_quote=}")

        return res

    async def _fill(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        ensure_size: bool,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        if size is not None:
            ctx = _Context(available=size, use_quote=False)
        elif quote is not None:
            ctx = _Context(available=quote, use_quote=True)
        else:
            raise ValueError("Neither size nor quote specified")

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
            except _FilledFromKeepAtBest:
                _log.debug("filled from keep limit order best task; cancelling track fills task")
                try:
                    await cancel(track_fills_task)
                except _FilledFromTrack:
                    pass
                _log.debug("cancelled track fills task")
            except _FilledFromTrack:
                _log.debug("filled from track fills task, cancelling keep limit order best task")
                try:
                    await cancel(keep_limit_order_best_task)
                except _FilledFromKeepAtBest:
                    pass
                _log.debug("cancelled keep limit order best task")
            except Exception:
                await cancel(keep_limit_order_best_task, track_fills_task)
                raise
            finally:
                if self._cancel_order_on_error and ctx.processing_order:
                    # Cancel active order.
                    _log.info(
                        f"cancelling active {symbol} {side.name} order "
                        f"{ctx.processing_order.client_id} at price {ctx.processing_order.price} "
                        f"size {ctx.processing_order.size}"
                    )
                    await self._try_cancel_order(
                        exchange=exchange,
                        account=account,
                        symbol=symbol,
                        client_id=ctx.processing_order.client_id,
                    )

        assert ctx.time >= 0
        return OrderResult(time=ctx.time, status=OrderStatus.FILLED, fills=ctx.fills)

    async def _track_fills(
        self,
        symbol: Symbol,
        stream: AsyncIterable[OrderUpdate.Any],
        side: Side,
        ctx: _Context,
    ) -> None:
        _log.info(f"tracking order updates for {symbol}")
        async for order in stream:
            if not ctx.requested_order:
                _log.debug(f"skipping {symbol} {side.name} order tracking; no active order")
                continue
            if (
                ctx.requested_order.client_id != order.client_id
                and ctx.processing_order
                and ctx.processing_order.client_id != order.client_id
            ):
                _log.debug(
                    f"skipping {symbol} {side.name} order tracking; {order.client_id=} != "
                    f"{ctx.requested_order.client_id=} nor processing order client id"
                )
                continue

            if isinstance(order, OrderUpdate.New):
                ctx.processing_order = ctx.requested_order
                ctx.fills_since_last_order.clear()
                deduct = ctx.processing_order.quote if ctx.use_quote else ctx.processing_order.size
                ctx.available -= deduct
                ctx.new_event.set()
                _log.info(
                    f"new {symbol} {side.name} order {ctx.processing_order.client_id} confirmed"
                )
            elif isinstance(order, OrderUpdate.Match):
                assert ctx.processing_order
                ctx.fills_since_last_order.append(order.fill)
                _log.info(
                    f"existing {symbol} {side.name} order {ctx.processing_order.client_id} matched"
                )
            elif isinstance(order, OrderUpdate.Cumulative):
                assert ctx.processing_order
                ctx.fills_since_last_order.append(
                    Fill.from_cumulative(
                        ctx.fills_since_last_order,
                        price=order.price,
                        cumulative_size=order.cumulative_size,
                        cumulative_quote=order.cumulative_quote,
                        cumulative_fee=order.cumulative_fee,
                        fee_asset=order.fee_asset,
                    )
                )
                _log.info(
                    f"existing {symbol} {side.name} order {ctx.processing_order.client_id} matched"
                )
            elif isinstance(order, OrderUpdate.Cancelled):
                assert ctx.processing_order
                ctx.fills.extend(ctx.fills_since_last_order)
                ctx.time = order.time
                ctx.available += ctx.get_add_back()
                ctx.cancelled_event.set()
                _log.info(
                    f"existing {symbol} {side.name} order {ctx.processing_order.client_id} "
                    "cancelled"
                )

                # Additional logging.
                filled_size_since_last_order = Fill.total_size(ctx.fills_since_last_order)
                size_to_be_filled = ctx.requested_order.size - filled_size_since_last_order
                _log.info(
                    f"last {symbol} {side.name} order size {ctx.processing_order.size} but filled "
                    f"{filled_size_since_last_order}; {size_to_be_filled} still to be filled"
                )

                ctx.processing_order = None
                # We also want to set requested order to none here because it may be that the
                # cancellation due to "order would be taker" may come through a websocket message
                # instead of the REST API call.
                if order.reason is CancelledReason.ORDER_WOULD_BE_TAKER:
                    ctx.requested_order = None
            elif isinstance(order, OrderUpdate.Done):
                assert ctx.processing_order
                ctx.fills.extend(ctx.fills_since_last_order)
                ctx.time = order.time
                ctx.done_event.set()
                _log.info(
                    f"existing {symbol} {side.name} order {ctx.processing_order.client_id} filled"
                )
                ctx.processing_order = None
                raise _FilledFromTrack()
            else:
                raise NotImplementedError(order)

    async def _keep_limit_order_best(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        ensure_size: bool,
        ctx: _Context,
    ) -> None:
        _log.info(
            f"managing {exchange} {symbol} limit order based on {self._order_placement_strategy} "
            "strategy"
        )
        _, filters = self._informant.get_fees_filters(exchange, symbol)
        can_edit_order = self._user.can_edit_order(exchange) and self._use_edit_order_if_possible
        async with self._orderbook.sync(exchange, symbol) as orderbook:
            while True:
                if ctx.wait_orderbook_update:
                    await orderbook.updated.wait()
                ctx.wait_orderbook_update = True

                if ctx.done_event.is_set():
                    break

                asks = orderbook.list_asks()
                bids = orderbook.list_bids()
                ob_side = bids if side is Side.BUY else asks
                ob_other_side = asks if side is Side.BUY else bids

                price = self._find_order_placement_price(
                    side, ob_side, ob_other_side, filters, ctx.requested_order
                )
                if price is None:  # None means we don't need to reposition our order.
                    continue

                if ctx.requested_order and not can_edit_order:
                    # Cancel prev order.
                    await self._cancel_order_and_wait(exchange, account, symbol, side, ctx)

                if ctx.requested_order and can_edit_order:
                    # Edit prev order (cancel + place in a single call).
                    await self._edit_order_and_wait(
                        exchange,
                        account,
                        symbol,
                        side,
                        price,
                        ensure_size,
                        ctx,
                    )
                else:
                    # Place new order.
                    await self._place_order_and_wait(
                        exchange,
                        account,
                        symbol,
                        side,
                        price,
                        ensure_size,
                        ctx,
                    )

    async def _place_order_and_wait(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        price: Decimal,
        ensure_size: bool,
        ctx: _Context,
    ) -> None:
        assert not ctx.requested_order
        client_id = self._user.generate_client_id(exchange)
        _, filters = self._informant.get_fees_filters(exchange, symbol)

        size = _get_size_for_price(symbol, side, filters, ensure_size, price, ctx.available, ctx)

        _log.info(f"placing {symbol} {side.name} order at price {price} for size {size}")
        ctx.requested_order = _ActiveOrder(
            client_id=client_id,
            price=price,
            size=size,
            quote=round_up(price * size, filters.quote_precision),
        )
        try:
            await self._user.place_order(
                exchange=exchange,
                account=account,
                symbol=symbol,
                side=side,
                type_=OrderType.LIMIT_MAKER,
                price=price,
                size=size,
                client_id=client_id,
            )
        except OrderWouldBeTaker:
            # Order would immediately match and take. Retry.
            _log.debug("place order; order would be taker")
            ctx.requested_order = None
            return

        _log.info(f"waiting for {symbol} {side.name} order {client_id} to be confirmed")
        try:
            await asyncio.wait_for(ctx.new_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
        except TimeoutError:
            _log.exception(
                f"timed out waiting for {symbol} {side.name} order {client_id} to be confirmed"
            )
            raise

    async def _edit_order_and_wait(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        price: Decimal,
        ensure_size: bool,
        ctx: _Context,
    ) -> None:
        assert ctx.requested_order
        prev_order = ctx.requested_order

        _, filters = self._informant.get_fees_filters(exchange, symbol)

        available = ctx.available + ctx.get_add_back()
        size = _get_size_for_price(symbol, side, filters, ensure_size, price, available, ctx)

        _log.info(
            f"editing {symbol} {side.name} order from price {prev_order.price} size "
            f"{prev_order.size} to price {price} size {size}"
        )
        new_order = _ActiveOrder(
            client_id=self._user.generate_client_id(exchange),
            price=price,
            size=size,
            quote=round_up(price * size, filters.quote_precision),
        )
        ctx.requested_order = new_order
        try:
            await self._user.edit_order(
                existing_id=prev_order.client_id,
                exchange=exchange,
                account=account,
                symbol=symbol,
                side=side,
                type_=OrderType.LIMIT_MAKER,
                price=price,
                size=size,
                client_id=new_order.client_id,
            )
        except OrderMissing:
            _log.debug("edit order; order missing")
            await asyncio.wait_for(ctx.cancelled_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
            ctx.requested_order = None
            ctx.wait_orderbook_update = False
            return
        except InsufficientFunds:
            _log.debug("edit order; insufficient funds")
            ctx.wait_orderbook_update = False
            if self._user.can_edit_order_atomic(exchange):
                ctx.requested_order = prev_order
            else:
                await asyncio.wait_for(ctx.cancelled_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
                ctx.requested_order = None
            return
        except OrderWouldBeTaker:
            _log.debug("edit order; order would be taker")
            # Order would immediately match and take. Retry.
            if self._user.can_edit_order_atomic(exchange):
                ctx.requested_order = prev_order
            else:
                await asyncio.wait_for(ctx.cancelled_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
                ctx.requested_order = None
            return

        # An edit request results in a CANCEL + NEW order updates.
        _log.info(
            f"waiting for {symbol} {side.name} order {prev_order.client_id} to be cancelled "
            f"and order {new_order.client_id} to be confirmed"
        )
        try:
            await asyncio.wait_for(ctx.cancelled_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
            await asyncio.wait_for(ctx.new_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
        except TimeoutError:
            _log.exception(
                f"timed out waiting for {symbol} {side.name} order {prev_order.client_id} to be "
                "edited"
            )
            raise

    async def _cancel_order_and_wait(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        ctx: _Context,
    ) -> None:
        assert ctx.requested_order
        client_id = ctx.requested_order.client_id
        _log.info(
            f"cancelling previous {symbol} {side.name} order {client_id} at price "
            f"{ctx.requested_order.price}"
        )
        if await self._try_cancel_order(
            exchange=exchange,
            account=account,
            symbol=symbol,
            client_id=client_id,
        ):
            _log.info(f"waiting for {symbol} {side.name} order {client_id} to be cancelled")
            try:
                await asyncio.wait_for(ctx.cancelled_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
            except TimeoutError:
                _log.exception(
                    f"timed out waiting for {symbol} {side.name} order "
                    f"{client_id} to be "
                    "cancelled"
                )
                raise
        else:
            _log.info(f"waiting for {symbol} {side.name} order {client_id} to be done")
            try:
                await asyncio.wait_for(ctx.done_event.wait(), _WS_EVENT_WAIT_TIMEOUT)
            except TimeoutError:
                _log.exception(
                    f"timed out waiting for {symbol} {side.name} order "
                    f"{client_id} to be "
                    "cancelled"
                )
                raise
        ctx.requested_order = None

    async def _try_cancel_order(
        self, exchange: str, account: Account, symbol: Symbol, client_id: str
    ) -> bool:
        try:
            await self._user.cancel_order(
                exchange=exchange,
                symbol=symbol,
                client_id=client_id,
                account=account,
            )
            return True
        except OrderMissing as exc:
            _log.warning(
                f"failed to cancel {symbol} order {client_id}; probably got filled; {exc}"
            )
            return False


# Always tries to match the highest order. Pulls back if highest pulls back.
def _match_highest(
    side: Side,
    ob_side: list[tuple[Decimal, Decimal]],
    ob_other_side: list[tuple[Decimal, Decimal]],
    filters: Filters,
    active_order: Optional[_ActiveOrder],
) -> Optional[Decimal]:
    _validate_side_not_empty(side, ob_side)

    closest_price, closest_size = ob_side[0]

    if active_order is None or active_order.price != closest_price:
        return closest_price
    elif active_order.size == closest_size and len(ob_side) > 1:
        next_to_closest_price = ob_side[1][0]
        return next_to_closest_price

    return None


# Always tries to be ahead of highest order. Does not pull back in case highest order pulls back.
def _leading_no_pullback(
    side: Side,
    ob_side: list[tuple[Decimal, Decimal]],
    ob_other_side: list[tuple[Decimal, Decimal]],
    filters: Filters,
    active_order: Optional[_ActiveOrder],
) -> Optional[Decimal]:
    _validate_side_not_empty(side, ob_side)

    op_step = operator.add if side is Side.BUY else operator.sub
    op_last_price_cmp = operator.gt if side is Side.BUY else operator.lt

    closest_price, closest_size = ob_side[0]
    if len(ob_other_side) == 0:
        # Set spread to an arbitrary value larger than step.
        spread = filters.price.step * 2
    else:
        closest_other_price = ob_other_side[0][0]
        spread = abs(closest_other_price - closest_price)

    if active_order is None:
        if spread == filters.price.step:
            return closest_price
        return op_step(closest_price, filters.price.step)

    if closest_price == active_order.price:
        if closest_size == active_order.size or spread == filters.price.step:
            return None
        return op_step(closest_price, filters.price.step)

    if op_last_price_cmp(closest_price, active_order.price):
        if spread == filters.price.step:
            return closest_price
        return op_step(closest_price, filters.price.step)

    return None


def _validate_side_not_empty(side: Side, ob_side: list[tuple[Decimal, Decimal]]) -> None:
    if len(ob_side) == 0:
        raise NotImplementedError(
            f'no existing {"bids" if side is Side.BUY else "asks"} in orderbook! cannot find '
            "optimal price"
        )


def _get_size_for_price(
    symbol: Symbol,
    side: Side,
    filters: Filters,
    ensure_size: bool,
    price: Decimal,
    available: Decimal,
    ctx: _Context,
) -> Decimal:
    # No need to round price as we take it from existing orders.

    size = available / price if ctx.use_quote else available
    size = filters.size.round_down(size)

    _log.info(f"validating {symbol} {side.name} order price and size")
    if len(ctx.fills) == 0:
        # We only want to raise an exception if the filters fail while we haven't had
        # any fills yet.
        try:
            filters.size.validate(size)
            filters.min_notional.validate_limit(price=price, size=size)
        except BadOrder as e:
            _log.error(e)
            raise
    else:
        try:
            filters.size.validate(size)
            filters.min_notional.validate_limit(price=price, size=size)
        except BadOrder as e:
            _log.info(f"{symbol} {side.name} price / size no longer valid: {e}")
            if ensure_size and Fill.total_size(ctx.fills) < ctx.original:
                size = filters.min_size(price)
                _log.info(f"increased size to {size}")
            else:
                raise _FilledFromKeepAtBest()
    return size
