import logging
from decimal import Decimal
from typing import Optional

from juno import Fill, OrderResult, OrderStatus, OrderType, OrderUpdate, Side, Symbol_
from juno.components import Informant, Orderbook, User

from .broker import Broker

_log = logging.getLogger(__name__)


# Differs from Market by listening for order fills over websocket. We should consolidate this
# logic into market broker an support differentiating between filling modes by capability or
# setting.
class Market2(Broker):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._user = user

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

        if not self._user.can_place_market_order(exchange):
            raise NotImplementedError()

        base_asset, quote_asset = Symbol_.assets(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            _log.info(
                f"buying {size} (ensure size: {ensure_size}) {symbol} with market order "
                f"({account} account)"
            )
            if ensure_size:
                size = filters.with_fee(size, fees.taker)
            return await self._fill(exchange, account, symbol, Side.BUY, size=size)
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
                return await self._fill(
                    exchange, account, symbol, Side.BUY, size=Fill.total_size(fills)
                )
            return await self._fill(exchange, account, symbol, Side.BUY, quote=quote)
        else:
            raise NotImplementedError()

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
        assert size is not None  # TODO: support by quote
        Broker.validate_funds(size, quote)

        if not self._user.can_place_market_order(exchange):
            raise NotImplementedError()

        _log.info(f"selling {size} {symbol} with market order ({account} account)")
        return await self._fill(exchange, account, symbol, Side.SELL, size=size)

    async def _fill(
        self,
        exchange: str,
        account: str,
        symbol: str,
        side: Side,
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
