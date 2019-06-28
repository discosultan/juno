import logging
from decimal import Decimal
from typing import List

from juno import Fill, Fills, OrderResult, OrderStatus, OrderType, Side
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


class Market:

    def __init__(self, informant: Informant, orderbook: Orderbook, exchanges: List[Exchange]
                 ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        fills = self.find_order_asks(exchange=exchange, symbol=symbol, quote=quote)
        return await self._fill(exchange=exchange, symbol=symbol, side=Side.ASK, fills=fills,
                                test=test)

    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        fills = self.find_order_bids(exchange=exchange, symbol=symbol, base=base)
        return await self._fill(exchange=exchange, symbol=symbol, side=Side.BID, fills=fills,
                                test=test)

    def find_order_asks(self, exchange: str, symbol: str, quote: Decimal) -> Fills:
        result = Fills()
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        for aprice, asize in self._orderbook.list_asks(exchange, symbol):
            aquote = aprice * asize
            base_asset, quote_asset = unpack_symbol(symbol)
            if aquote >= quote:
                size = filters.size.round_down(quote / aprice)
                if size != Decimal(0):
                    # TODO: Fee should also be rounded.
                    fee = aprice * size * fees.taker
                    result.append(Fill(price=aprice, size=size, fee=fee, fee_asset=base_asset))
                break
            else:
                assert asize != Decimal(0)
                fee = aprice * asize * fees.taker
                result.append(Fill(price=aprice, size=asize, fee=fee, fee_asset=base_asset))
                quote -= aquote
        return result

    def find_order_bids(self, exchange: str, symbol: str, base: Decimal) -> Fills:
        result = Fills()
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)
        for bprice, bsize in self._orderbook.list_bids(exchange, symbol):
            base_asset, quote_asset = unpack_symbol(symbol)
            if bsize >= base:
                size = filters.size.round_down(base)
                if size != Decimal(0):
                    fee = bprice * size * fees.taker
                    result.append(Fill(price=bprice, size=size, fee=fee, fee_asset=quote_asset))
                break
            else:
                assert bsize != Decimal(0)
                fee = bprice * bsize * fees.taker
                result.append(Fill(price=bprice, size=bsize, fee=fee, fee_asset=quote_asset))
                base -= bsize
        return result

    async def _fill(self, exchange: str, symbol: str, side: Side, fills: Fills, test: bool
                    ) -> OrderResult:
        if fills.total_size == 0:
            _log.info('skipping market order placement; size zero')
            return OrderResult.not_placed()

        _log.info(f'placing market {side} order of size {fills.total_size}')
        res = await self._exchanges[exchange].place_order(
            symbol=symbol,
            side=side,
            type_=OrderType.MARKET,
            size=fills.total_size,
            test=test)
        if test:
            res = OrderResult(
                status=OrderStatus.FILLED,
                fills=fills)
        return res
