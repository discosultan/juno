import logging
from decimal import Decimal
from typing import List, Optional

from juno import Fill, OrderResult, OrderStatus, OrderType, Side
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange
from juno.math import round_half_up
from juno.utils import unpack_symbol

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
        res = await self._place_order(
            exchange=exchange, symbol=symbol, side=Side.BUY, size=size, test=test, margin=margin
        )
        if test:
            fills = self.find_order_asks(exchange=exchange, symbol=symbol, size=size)
            self._validate_fills(exchange, symbol, fills)
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    async def buy_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        exchange_instance = self._exchanges[exchange]

        if test or not exchange_instance.can_place_order_market_quote:
            fills = self.find_order_asks_by_quote(exchange=exchange, symbol=symbol, quote=quote)
            self._validate_fills(exchange, symbol, fills)

        if exchange_instance.can_place_order_market_quote:
            res = await self._place_order(
                exchange=exchange, symbol=symbol, side=Side.BUY, quote=quote, test=test,
                margin=margin
            )
        else:
            res = await self._place_order(
                exchange=exchange, symbol=symbol, side=Side.BUY, size=Fill.total_size(fills),
                test=test, margin=margin
            )
        if test:
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    async def sell(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        res = await self._place_order(
            exchange=exchange, symbol=symbol, side=Side.SELL, size=size, test=test, margin=margin
        )
        if test:
            fills = self.find_order_bids(exchange=exchange, symbol=symbol, size=size)
            self._validate_fills(exchange, symbol, fills)
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res

    def find_order_asks(self, exchange: str, symbol: str, size: Decimal) -> List[Fill]:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for aprice, asize in self._orderbook.list_asks(exchange, symbol):
            if asize >= size:
                fee = round_half_up(size * fees.taker, filters.base_precision)
                result.append(Fill.with_computed_quote(
                    price=aprice, size=size, fee=fee, fee_asset=base_asset,
                    precision=filters.quote_precision
                ))
                break
            else:
                fee = round_half_up(asize * fees.taker, filters.base_precision)
                result.append(Fill.with_computed_quote(
                    price=aprice, size=asize, fee=fee, fee_asset=base_asset,
                    precision=filters.quote_precision
                ))
                size -= asize
        return result

    def find_order_asks_by_quote(self, exchange: str, symbol: str, quote: Decimal) -> List[Fill]:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for aprice, asize in self._orderbook.list_asks(exchange, symbol):
            aquote = aprice * asize
            if aquote >= quote:
                size = filters.size.round_down(quote / aprice)
                if size != 0:
                    fee = round_half_up(size * fees.taker, filters.base_precision)
                    result.append(Fill.with_computed_quote(
                        price=aprice, size=size, fee=fee, fee_asset=base_asset,
                        precision=filters.quote_precision
                    ))
                break
            else:
                assert asize != 0
                fee = round_half_up(asize * fees.taker, filters.base_precision)
                result.append(Fill.with_computed_quote(
                    price=aprice, size=asize, fee=fee, fee_asset=base_asset,
                    precision=filters.quote_precision
                ))
                quote -= aquote
        return result

    def find_order_bids(self, exchange: str, symbol: str, size: Decimal) -> List[Fill]:
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        result = []
        base_asset, quote_asset = unpack_symbol(symbol)
        for bprice, bsize in self._orderbook.list_bids(exchange, symbol):
            if bsize >= size:
                rsize = filters.size.round_down(size)
                if size != 0:
                    fee = round_half_up(bprice * rsize * fees.taker, filters.quote_precision)
                    result.append(Fill.with_computed_quote(
                        price=bprice, size=rsize, fee=fee, fee_asset=quote_asset,
                        precision=filters.quote_precision
                    ))
                break
            else:
                assert bsize != 0
                fee = round_half_up(bprice * bsize * fees.taker, filters.quote_precision)
                result.append(Fill.with_computed_quote(
                    price=bprice, size=bsize, fee=fee, fee_asset=quote_asset,
                    precision=filters.quote_precision
                ))
                size -= bsize
        return result

    def _validate_fills(self, exchange: str, symbol: str, fills: List[Fill]) -> None:
        _fees, filters = self._informant.get_fees_filters(exchange, symbol)
        size = Fill.total_size(fills)
        filters.size.validate(size)
        # TODO: Calc avg price over `filters.min_notional.avg_price_period` minutes.
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#min_notional
        filters.min_notional.validate_market(avg_price=fills[0].price, size=size)

    async def _place_order(
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
        return await self._exchanges[exchange].place_order(
            symbol=symbol, side=side, type_=OrderType.MARKET, size=size, quote=quote, test=test,
            margin=margin
        )
