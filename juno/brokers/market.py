import logging
from decimal import Decimal
from typing import Callable, Optional

from juno import (
    Account,
    Fill,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    Side,
    Symbol,
    Symbol_,
    Timestamp_,
)
from juno.components import Informant, Orderbook, User

from .broker import Broker

_log = logging.getLogger(__name__)


class Market(Broker):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        get_time_ms: Callable[[], int] = Timestamp_.now,
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._user = user
        self._get_time_ms = get_time_ms

        if not user.can_place_market_order_quote("__all__"):
            _log.warning(
                "not all exchanges support placing market orders by quote size; for them, "
                "calculating size by quote from orderbook instead"
            )

    async def buy(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        ensure_size: bool = False,
        leverage: Optional[int] = None,
        reduce_only: Optional[bool] = None,
    ) -> OrderResult:
        Broker.validate_funds(size, quote)

        if not self._user.can_place_market_order(exchange):
            raise NotImplementedError()

        if self._user.can_get_market_order_result_direct(exchange):
            return await self._buy(
                exchange=exchange,
                account=account,
                symbol=symbol,
                size=size,
                quote=quote,
                test=test,
                ensure_size=ensure_size,
                leverage=leverage,
                reduce_only=reduce_only,
            )
        else:
            return await self._buy_ws(
                exchange=exchange,
                account=account,
                symbol=symbol,
                size=size,
                quote=quote,
                test=test,
                ensure_size=ensure_size,
                leverage=leverage,
                reduce_only=reduce_only,
            )

    async def sell(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        leverage: Optional[int] = None,
        reduce_only: Optional[bool] = None,
    ) -> OrderResult:
        assert size is not None  # TODO: support by quote
        Broker.validate_funds(size, quote)

        if not self._user.can_place_market_order(exchange):
            raise NotImplementedError()

        if self._user.can_get_market_order_result_direct(exchange):
            return await self._sell(
                exchange=exchange,
                account=account,
                symbol=symbol,
                size=size,
                quote=quote,
                test=test,
                leverage=leverage,
                reduce_only=reduce_only,
            )
        else:
            return await self._sell_ws(
                exchange=exchange,
                account=account,
                symbol=symbol,
                size=size,
                quote=quote,
                test=test,
                leverage=leverage,
                reduce_only=reduce_only,
            )

    async def _buy(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal],
        quote: Optional[Decimal],
        test: bool,
        ensure_size: bool,
        leverage: Optional[int],
        reduce_only: Optional[bool],
    ) -> OrderResult:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            if ensure_size:
                size = filters.with_fee(size, fees.taker)
            size = filters.size.round_down(size)
            if test:
                res = OrderResult(
                    time=self._get_time_ms(),
                    status=OrderStatus.FILLED,
                    fills=await self._get_buy_fills(exchange, symbol, size=size),
                )
            else:
                res = await self._fill(
                    exchange=exchange,
                    symbol=symbol,
                    side=Side.BUY,
                    size=size,
                    account=account,
                    leverage=leverage,
                    reduce_only=reduce_only,
                )
        elif quote is not None:
            if test:
                res = OrderResult(
                    time=self._get_time_ms(),
                    status=OrderStatus.FILLED,
                    fills=await self._get_buy_fills(exchange, symbol, quote=quote),
                )
            elif self._user.can_place_market_order_quote(exchange):
                res = await self._fill(
                    exchange=exchange,
                    account=account,
                    symbol=symbol,
                    side=Side.BUY,
                    quote=quote,
                    leverage=leverage,
                    reduce_only=reduce_only,
                )
            else:
                res = await self._fill(
                    exchange=exchange,
                    account=account,
                    symbol=symbol,
                    side=Side.BUY,
                    size=Fill.total_size(await self._get_buy_fills(exchange, symbol, quote=quote)),
                    leverage=leverage,
                    reduce_only=reduce_only,
                )
        else:
            raise NotImplementedError()

        return res

    async def _sell(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal],
        quote: Optional[Decimal],
        test: bool,
        leverage: Optional[int],
        reduce_only: Optional[bool],
    ) -> OrderResult:
        assert size is not None  # TODO: support by quote

        _, filters = self._informant.get_fees_filters(exchange, symbol)
        size = filters.size.round_down(size)

        if test:
            res = OrderResult(
                time=self._get_time_ms(),
                status=OrderStatus.FILLED,
                fills=await self._get_sell_fills(exchange, symbol, size=size),
            )
        else:
            res = await self._fill(
                exchange=exchange,
                account=account,
                symbol=symbol,
                side=Side.SELL,
                size=size,
                leverage=leverage,
                reduce_only=reduce_only,
            )

        return res

    async def _get_buy_fills(
        self,
        exchange: str,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> list[Fill]:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        async with self._orderbook.sync(exchange, symbol) as orderbook:
            fills = orderbook.find_order_asks(
                size=size, quote=quote, fee_rate=fees.taker, filters=filters
            )
        self._validate_fills(exchange, symbol, fills)
        return fills

    async def _get_sell_fills(
        self,
        exchange: str,
        symbol: Symbol,
        size: Decimal,
    ) -> list[Fill]:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        async with self._orderbook.sync(exchange, symbol) as orderbook:
            fills = orderbook.find_order_bids(size=size, fee_rate=fees.taker, filters=filters)
        self._validate_fills(exchange, symbol, fills)
        return fills

    def _validate_fills(self, exchange: str, symbol: Symbol, fills: list[Fill]) -> None:
        _, filters = self._informant.get_fees_filters(exchange, symbol)
        size = Fill.total_size(fills)
        filters.size.validate(size)
        # TODO: Calc avg price over `filters.min_notional.avg_price_period` minutes.
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#min_notional
        filters.min_notional.validate_market(avg_price=fills[0].price, size=size)

    async def _fill(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        leverage: Optional[int],
        reduce_only: Optional[bool],
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        # TODO: If we tracked Binance fills with websocket, we could also get filled quote sizes.
        # Now we need to calculate ourselves.
        order_log = f"market {side.name} order"
        fill_log = f"{size} size" if size is not None else f"{quote} quote"
        _log.info(f"placing {symbol} {order_log} to fill {fill_log}")
        res = await self._user.place_order(
            exchange=exchange,
            symbol=symbol,
            side=side,
            type_=OrderType.MARKET,
            size=size,
            quote=quote,
            account=account,
            leverage=leverage,
            reduce_only=reduce_only,
        )
        assert res.status is OrderStatus.FILLED
        return res

    # Websocket approach.

    async def _buy_ws(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal],
        quote: Optional[Decimal],
        test: bool,
        ensure_size: bool,
        leverage: Optional[int],
        reduce_only: Optional[bool],
    ) -> OrderResult:
        assert not test

        base_asset, quote_asset = Symbol_.assets(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            _log.info(
                f"buying {size} (ensure size: {ensure_size}) {symbol} with market order "
                f"({account} account)"
            )
            if ensure_size:
                size = filters.with_fee(size, fees.taker)
            return await self._fill_ws(
                exchange,
                account,
                symbol,
                Side.BUY,
                size=size,
                leverage=leverage,
                reduce_only=reduce_only,
            )
        elif quote is not None:
            _log.info(
                f"buying {quote} {quote_asset} worth of {base_asset} with {symbol} market order "
                f"({account} account)"
            )
            if not self._user.can_place_market_order_quote(exchange):
                async with self._orderbook.sync(exchange, symbol) as orderbook:
                    fills = orderbook.find_order_asks(
                        quote=quote, fee_rate=fees.taker, filters=filters
                    )
                return await self._fill_ws(
                    exchange,
                    account,
                    symbol,
                    Side.BUY,
                    size=Fill.total_size(fills),
                    leverage=leverage,
                    reduce_only=reduce_only,
                )
            return await self._fill_ws(
                exchange,
                account,
                symbol,
                Side.BUY,
                quote=quote,
                leverage=leverage,
                reduce_only=reduce_only,
            )
        else:
            raise NotImplementedError()

    async def _sell_ws(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal],
        quote: Optional[Decimal],
        test: bool,
        leverage: Optional[int],
        reduce_only: Optional[bool],
    ) -> OrderResult:
        assert not test
        assert size is not None  # TODO: support by quote

        _log.info(f"selling {size} {symbol} with market order ({account} account)")
        return await self._fill_ws(
            exchange,
            account,
            symbol,
            Side.SELL,
            size=size,
            leverage=leverage,
            reduce_only=reduce_only,
        )

    async def _fill_ws(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        side: Side,
        leverage: Optional[int],
        reduce_only: Optional[bool],
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        if size is not None:
            _, filters = self._informant.get_fees_filters(exchange, symbol)
            size = filters.size.round_down(size)
            filters.size.validate(size)

        client_id = self._user.generate_client_id(exchange)

        async with self._user.connect_stream_orders(
            exchange=exchange, account=account, symbol=symbol
        ) as stream:
            await self._user.place_order(
                exchange=exchange,
                account=account,
                symbol=symbol,
                side=side,
                type_=OrderType.MARKET,
                size=size,
                quote=quote,
                client_id=client_id,
                leverage=leverage,
                reduce_only=reduce_only,
            )

            fills = []  # Fills from aggregated trades.
            time = -1
            async for order in stream:
                if order.client_id != client_id:
                    _log.debug(
                        f"skipping {symbol} {side.name} order tracking; {order.client_id=} != "
                        f"{client_id=}"
                    )
                    continue

                if isinstance(order, OrderUpdate.New):
                    _log.info(f"new {symbol} {side.name} order {client_id} confirmed")
                elif isinstance(order, OrderUpdate.Match):
                    _log.info(f"existing {symbol} {side.name} order {client_id} matched")
                    fills.append(order.fill)
                elif isinstance(order, OrderUpdate.Cumulative):
                    _log.info(f"existing {symbol} {side.name} order {client_id} matched")
                    fills.append(
                        Fill.from_cumulative(
                            fills,
                            price=order.price,
                            cumulative_size=order.cumulative_size,
                            cumulative_quote=order.cumulative_quote,
                            cumulative_fee=order.cumulative_fee,
                            fee_asset=order.fee_asset,
                        )
                    )
                elif isinstance(order, OrderUpdate.Done):
                    _log.info(f"existing {symbol} {side.name} order {client_id} filled")
                    time = order.time
                    break
                else:
                    raise NotImplementedError(order)

        return OrderResult(time=time, status=OrderStatus.FILLED, fills=fills)
