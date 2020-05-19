import logging
from decimal import Decimal
from typing import List, Optional

from juno import Fill, OrderResult, OrderStatus, OrderType, Side
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange

from .broker import Broker

_log = logging.getLogger(__name__)


class Market(Broker):
    def __init__(
        self, informant: Informant, orderbook: Orderbook, exchanges: List[Exchange]
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

        for name, exchange in self._exchanges.items():
            if not exchange.can_place_order_market_quote:
                _log.warning(
                    f'{name} does not support placing market orders by quote size; calculating '
                    'size by quote from orderbook instead'
                )

    async def buy(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = filters.size.round_down(size)

        res = await self._fill(
            exchange=exchange, symbol=symbol, side=Side.BUY, size=size, test=test, margin=margin
        )
        if test:
            await self._orderbook.ensure_sync([exchange], [symbol])
            fills = self._orderbook.find_order_asks(
                exchange=exchange, symbol=symbol, size=size, fee_rate=fees.taker, filters=filters
            )
            self._validate_fills(exchange, symbol, fills)
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    async def buy_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        exchange_instance = self._exchanges[exchange]

        if test or not exchange_instance.can_place_order_market_quote:
            await self._orderbook.ensure_sync([exchange], [symbol])
            fees, filters = self._informant.get_fees_filters(exchange, symbol)
            fills = self._orderbook.find_order_asks_by_quote(
                exchange=exchange, symbol=symbol, quote=quote, fee_rate=fees.taker, filters=filters
            )
            self._validate_fills(exchange, symbol, fills)

        if exchange_instance.can_place_order_market_quote:
            res = await self._fill(
                exchange=exchange, symbol=symbol, side=Side.BUY, quote=quote, test=test,
                margin=margin
            )
        else:
            res = await self._fill(
                exchange=exchange, symbol=symbol, side=Side.BUY, size=Fill.total_size(fills),
                test=test, margin=margin
            )
        if test:
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    async def sell(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = filters.size.round_down(size)

        res = await self._fill(
            exchange=exchange, symbol=symbol, side=Side.SELL, size=size, test=test, margin=margin
        )
        if test:
            await self._orderbook.ensure_sync([exchange], [symbol])
            fills = self._orderbook.find_order_bids(
                exchange=exchange, symbol=symbol, size=size, fee_rate=fees.taker, filters=filters
            )
            self._validate_fills(exchange, symbol, fills)
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    def _validate_fills(self, exchange: str, symbol: str, fills: List[Fill]) -> None:
        _fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = Fill.total_size(fills)
        filters.size.validate(size)
        # TODO: Calc avg price over `filters.min_notional.avg_price_period` minutes.
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#min_notional
        filters.min_notional.validate_market(avg_price=fills[0].price, size=size)

    async def _fill(
        self,
        exchange: str,
        symbol: str,
        side: Side,
        test: bool,
        margin: bool,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        # TODO: If we tracked Binance fills with websocket, we could also get filled quote sizes.
        # Now we need to calculate ourselves.
        order_log = f'{"test " if test else ""}market {side.name} order'
        fill_log = f'{size} size' if size is not None else f'{quote} quote'
        _log.info(f'placing {order_log} to fill {fill_log}')
        res = await self._exchanges[exchange].place_order(
            symbol=symbol, side=side, type_=OrderType.MARKET, size=size, quote=quote, test=test,
            margin=margin
        )
        assert test or res.status is OrderStatus.FILLED
        return res
