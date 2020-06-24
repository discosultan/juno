import logging
import uuid
from decimal import Decimal
from typing import Callable, List, Optional

from juno import Fill, OrderResult, OrderStatus, OrderType, OrderUpdate, Side
from juno.components import Informant, Orderbook
from juno.exchanges import Exchange
from juno.utils import unpack_symbol

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
        exchanges: List[Exchange],
        get_client_id: Callable[[], str] = lambda: str(uuid.uuid4())
    ) -> None:
        self._informant = informant
        self._orderbook = orderbook
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_client_id = get_client_id

    async def buy(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        _log.info(f'buying {size} {symbol} with market order')
        return await self._fill(exchange, symbol, Side.BUY, margin, size=size)

    async def buy_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        base_asset, quote_asset = unpack_symbol(symbol)
        _log.info(f'buying {quote} {quote_asset} worth of {base_asset} with {symbol} market order')
        exchange_instance = self._exchanges[exchange]
        if not exchange_instance.can_place_order_market_quote:
            await self._orderbook.ensure_sync([exchange], [symbol])
            fees, filters = self._informant.get_fees_filters(exchange, symbol)
            fills = self._orderbook.find_order_asks_by_quote(
                exchange, symbol, quote, fees.taker, filters
            )
            return await self._fill(
                exchange, symbol, Side.BUY, margin, size=Fill.total_size(fills)
            )
        return await self._fill(exchange, symbol, Side.BUY, margin, quote=quote)

    async def sell(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        assert not test
        _log.info(f'selling {size} {symbol} with market order')
        return await self._fill(exchange, symbol, Side.SELL, margin, size=size)

    async def _fill(
        self,
        exchange: str,
        symbol: str,
        side: Side,
        margin: bool,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
    ) -> OrderResult:
        if size is not None:
            _fees, filters = self._informant.get_fees_filters(exchange, symbol)
            size = filters.size.round_down(size)
            filters.size.validate(size)

        client_id = self._get_client_id()
        exchange_instance = self._exchanges[exchange]

        async with exchange_instance.connect_stream_orders(
            symbol=symbol, margin=margin
        ) as stream:
            await exchange_instance.place_order(
                symbol=symbol,
                side=side,
                type_=OrderType.MARKET,
                size=size,
                quote=quote,
                client_id=client_id,
                margin=margin,
                test=False,
            )

            fills = []  # Fills from aggregated trades.
            time = -1
            async for order in stream:
                if order.client_id != client_id:
                    _log.debug(
                        f'skipping {symbol} order tracking; {order.client_id=} != {client_id=}'
                    )
                    continue

                if isinstance(order, OrderUpdate.New):
                    _log.info(f'received new confirmation for {symbol} order {client_id}')
                elif isinstance(order, OrderUpdate.Match):
                    _log.info(f'existing {symbol} order {client_id} match')
                    fills.append(order.fill)
                elif isinstance(order, OrderUpdate.Done):
                    _log.info(f'existing {symbol} order {client_id} filled')
                    time = order.time
                    break
                else:
                    raise NotImplementedError(order)

        return OrderResult(time=time, status=OrderStatus.FILLED, fills=fills)
