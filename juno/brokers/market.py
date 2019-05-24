import logging
from decimal import Decimal
from typing import List

from juno import Fills, OrderResult, OrderStatus, OrderType, Side
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange

_log = logging.getLogger(__name__)


class Market:

    def __init__(self, informant: Informant, orderbook: Orderbook, exchanges: List[Exchange]
                 ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        fills = self._orderbook.find_order_asks(exchange=exchange, symbol=symbol, quote=quote)
        return await self._fill(exchange=exchange, symbol=symbol, side=Side.BUY, fills=fills,
                                test=test)

    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        fills = self._orderbook.find_order_bids(exchange=exchange, symbol=symbol, base=base)
        return await self._fill(exchange=exchange, symbol=symbol, side=Side.SELL, fills=fills,
                                test=test)

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
                status=OrderStatus.NOT_PLACED,
                fills=fills)
        return res
