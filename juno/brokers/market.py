import logging
from decimal import Decimal
from typing import List

from juno import Fill, InsufficientBalance, OrderResult, OrderStatus, OrderType, Side
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

    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        fills = self.find_order_asks(exchange=exchange, symbol=symbol, quote=quote)
        return await self._fill(
            exchange=exchange, symbol=symbol, side=Side.BUY, fills=fills, test=test
        )

    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        fills = self.find_order_bids(exchange=exchange, symbol=symbol, base=base)
        return await self._fill(
            exchange=exchange, symbol=symbol, side=Side.SELL, fills=fills, test=test
        )

    def find_order_asks(self, exchange: str, symbol: str, quote: Decimal) -> List[Fill]:
        result = []
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        for aprice, asize in self._orderbook.list_asks(exchange, symbol):
            aquote = aprice * asize
            base_asset, quote_asset = unpack_symbol(symbol)
            if aquote >= quote:
                size = filters.size.round_down(quote / aprice)
                if size != 0:
                    fee = round_half_up(size * fees.taker, filters.base_precision)
                    result.append(Fill(price=aprice, size=size, fee=fee, fee_asset=base_asset))
                break
            else:
                assert asize != 0
                fee = round_half_up(asize * fees.taker, filters.base_precision)
                result.append(Fill(price=aprice, size=asize, fee=fee, fee_asset=base_asset))
                quote -= aquote
        return result

    def find_order_bids(self, exchange: str, symbol: str, base: Decimal) -> List[Fill]:
        result = []
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        for bprice, bsize in self._orderbook.list_bids(exchange, symbol):
            base_asset, quote_asset = unpack_symbol(symbol)
            if bsize >= base:
                size = filters.size.round_down(base)
                if size != 0:
                    fee = round_half_up(bprice * size * fees.taker, filters.quote_precision)
                    result.append(Fill(price=bprice, size=size, fee=fee, fee_asset=quote_asset))
                break
            else:
                assert bsize != 0
                fee = round_half_up(bprice * bsize * fees.taker, filters.quote_precision)
                result.append(Fill(price=bprice, size=bsize, fee=fee, fee_asset=quote_asset))
                base -= bsize
        return result

    async def _fill(
        self, exchange: str, symbol: str, side: Side, fills: List[Fill], test: bool
    ) -> OrderResult:
        order_log = f'{"test " if test else ""}market {side} order'

        if Fill.total_size(fills) == 0:
            _log.info(f'skipping {order_log} placement; size zero')
            raise InsufficientBalance()

        _log.info(f'placing {order_log} of size {Fill.total_size(fills)}')
        res = await self._exchanges[exchange].place_order(
            symbol=symbol, side=side, type_=OrderType.MARKET, size=Fill.total_size(fills),
            test=test
        )
        if test:
            res = OrderResult(status=OrderStatus.FILLED, fills=fills)
        return res
