import logging
from decimal import Decimal
from typing import Callable, Optional

from juno import Fill, OrderResult, OrderStatus, OrderType, Side
from juno.components import Informant, Orderbook, User
from juno.time import time_ms

from .broker import Broker

_log = logging.getLogger(__name__)


class Market(Broker):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._user = user
        self._get_time_ms = get_time_ms

        if not orderbook.can_place_order_market_quote('__all__'):
            _log.warning(
                'not all exchanges support placing market orders by quote size; for them, '
                'calculating size by quote from orderbook instead'
            )

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
        Broker.validate_funds(size, quote)

        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        if size is not None:
            if ensure_size:
                size = filters.with_fee(size, fees.taker)
            size = filters.size.round_down(size)
            if test:
                async with self._orderbook.sync(exchange, symbol) as orderbook:
                    fills = orderbook.find_order_asks(
                        size=size, fee_rate=fees.taker, filters=filters
                    )
                self._validate_fills(exchange, symbol, fills)
                res = OrderResult(time=self._get_time_ms(), status=OrderStatus.FILLED, fills=fills)
            else:
                res = await self._fill(
                    exchange=exchange, symbol=symbol, side=Side.BUY, size=size, account=account
                )
        elif quote is not None:
            if test or not self._orderbook.can_place_order_market_quote(exchange):
                fees, filters = self._informant.get_fees_filters(exchange, symbol)
                async with self._orderbook.sync(exchange, symbol) as orderbook:
                    fills = orderbook.find_order_asks(
                        quote=quote, fee_rate=fees.taker, filters=filters
                    )
                self._validate_fills(exchange, symbol, fills)

            if test:
                res = OrderResult(time=self._get_time_ms(), status=OrderStatus.FILLED, fills=fills)
            else:
                if self._orderbook.can_place_order_market_quote(exchange):
                    res = await self._fill(
                        exchange=exchange, account=account, symbol=symbol, side=Side.BUY,
                        quote=quote
                    )
                else:
                    res = await self._fill(
                        exchange=exchange, account=account, symbol=symbol, side=Side.BUY,
                        size=Fill.total_size(fills)
                    )
        else:
            raise NotImplementedError()

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
        assert size  # TODO: support by quote
        Broker.validate_funds(size, quote)

        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = filters.size.round_down(size)

        if test:
            async with self._orderbook.sync(exchange, symbol) as orderbook:
                fills = orderbook.find_order_bids(
                    size=size, fee_rate=fees.taker, filters=filters
                )
            self._validate_fills(exchange, symbol, fills)
            res = OrderResult(time=self._get_time_ms(), status=OrderStatus.FILLED, fills=fills)
        else:
            res = await self._fill(
                exchange=exchange, account=account, symbol=symbol, side=Side.SELL, size=size
            )

        return res

    def _validate_fills(self, exchange: str, symbol: str, fills: list[Fill]) -> None:
        _fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = Fill.total_size(fills)
        filters.size.validate(size)
        # TODO: Calc avg price over `filters.min_notional.avg_price_period` minutes.
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#min_notional
        filters.min_notional.validate_market(avg_price=fills[0].price, size=size)

    async def _fill(
        self,
        exchange: str,
        account: str,
        symbol: str,
        side: Side,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        # TODO: If we tracked Binance fills with websocket, we could also get filled quote sizes.
        # Now we need to calculate ourselves.
        order_log = f'market {side.name} order'
        fill_log = f'{size} size' if size is not None else f'{quote} quote'
        _log.info(f'placing {symbol} {order_log} to fill {fill_log}')
        res = await self._user.place_order(
            exchange=exchange,
            symbol=symbol,
            side=side,
            type_=OrderType.MARKET,
            size=size,
            quote=quote,
            account=account,
        )
        assert res.status is OrderStatus.FILLED
        return res
