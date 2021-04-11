from __future__ import annotations

import time
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import Any, AsyncIterable, AsyncIterator, Optional

from juno.common import (
    Balance, Candle, Depth, ExchangeInfo, Fees, Fill, Filters, Side, OrderResult, OrderStatus,
    OrderType, OrderUpdate, TimeInForce
)
from juno.filters import Price, Size
from juno.http import ClientSession

from .exchange import Exchange

# https://www.gate.io/docs/apiv4/en/index.html#gate-api-v4
_API_URL = 'https://api.gateio.ws/api/v4'
_WS_URL = 'wss://api.gateio.ws/ws/v4'


class GateIO(Exchange):
    def __init__(self, high_precision: bool = True) -> None:
        self._high_precision = high_precision
        self._session = ClientSession(raise_for_status=True, name=type(self).__name__)

    async def __aenter__(self) -> GateIO:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://www.gate.io/docs/apiv4/en/index.html#list-all-currency-pairs-supported
        content = await self._request_json('GET', '/spot/currency_pairs')

        fees, filters = {}, {}
        for pair in (c for c in content if c['trade_status'] == 'tradable'):
            symbol = _from_symbol(pair['id'])
            # TODO: Take into account different fee levels. Currently only worst level.
            fee = Decimal(pair['fee']) / 100
            fees[symbol] = Fees(maker=fee, taker=fee)
            filters[symbol] = Filters(
                base_precision=pair['precision'],
                quote_precision=pair['amount_precision'],
                size=Size(
                    min=(
                        Decimal('0.0') if (min_base_amount := pair.get('min_base_amount')) is None
                        else Decimal(min_base_amount)
                    ),
                ),
                price=Price(
                    min=(
                        Decimal('0.0')
                        if (min_quote_amount := pair.get('min_quote_amount')) is None
                        else Decimal(min_quote_amount)
                    ),
                )
            )

        return ExchangeInfo(
            fees=fees,
            filters=filters,
        )

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # https://www.gate.io/docs/apiv4/en/index.html#retrieve-order-book
        content = await self._request_json(
            'GET',
            '/spot/order_book',
            params={'currency_pair': _to_symbol(symbol)},
        )
        return Depth.Snapshot(
            asks=[(Decimal(price), Decimal(size)) for price, size in content['asks']],
            bids=[(Decimal(price), Decimal(size)) for price, size in content['bids']],
        )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        # https://www.gateio.pro/docs/apiv4/ws/index.html#changed-order-book-levels
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for data in ws:
                yield Depth.Update(
                    bids=[(Decimal(price), Decimal(size)) for price, size in data['b']],
                    asks=[(Decimal(price), Decimal(size)) for price, size in data['a']],
                    first_id=data['U'],
                    last_id=data['u'],
                )

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            await ws.send_json({
                'time': int(time.time()),
                'channel': 'spot.order_book_update',
                'event': 'subscribe',  # 'unsubscribe' for unsubscription
                'payload': [_to_symbol(symbol), '100ms' if self._high_precision else '1000ms'],
            })
            yield inner(ws)

    async def place_order(
        self,
        account: str,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        assert account == 'spot'
        raise NotImplementedError()

        # data: dict[str, Any] = {
        #     'symbol': _to_symbol(symbol),
        #     'side': _to_side(side),
        #     'type': _to_order_type(type_),
        # }
        # if size is not None:
        #     data['quantity'] = _to_decimal(size)
        # if quote is not None:
        #     data['quoteOrderQty'] = _to_decimal(quote)
        # if price is not None:
        #     data['price'] = _to_decimal(price)
        # if time_in_force is not None:
        #     data['timeInForce'] = _to_time_in_force(time_in_force)
        # if client_id is not None:
        #     data['newClientOrderId'] = client_id
        # if account not in ['spot', 'margin']:
        #     data['isIsolated'] = 'TRUE'
        # url = '/api/v3/order' if account == 'spot' else '/sapi/v1/margin/order'
        # _, content = await self._api_request('POST', url, data=data, security=_SEC_TRADE)

        # # In case of LIMIT_MARKET order, the following are not present in the response:
        # # - status
        # # - cummulativeQuoteQty
        # # - fills
        # total_quote = Decimal(q) if (q := content.get('cummulativeQuoteQty')) else Decimal('0.0')
        # return OrderResult(
        #     time=content['transactTime'],
        #     status=(
        #         _from_order_status(status) if (status := content.get('status'))
        #         else OrderStatus.NEW
        #     ),
        #     fills=[
        #         Fill(
        #             price=(p := Decimal(f['price'])),
        #             size=(s := Decimal(f['qty'])),
        #             quote=(p * s).quantize(total_quote),
        #             fee=Decimal(f['commission']),
        #             fee_asset=f['commissionAsset'].lower()
        #         ) for f in content.get('fills', [])
        #     ]
        # )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        assert account == 'spot'
        raise NotImplementedError()

        # url = '/api/v3/order' if account == 'spot' else '/sapi/v1/margin/order'
        # data = {
        #     'symbol': _to_symbol(symbol),
        #     'origClientOrderId': client_id,
        # }
        # if account not in ['spot', 'margin']:
        #     data['isIsolated'] = 'TRUE'
        # await self._api_request('DELETE', url, data=data, security=_SEC_TRADE)

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'
        raise NotImplementedError()

        # async def inner(stream: AsyncIterable[dict[str, Any]]) -> AsyncIterable[OrderUpdate.Any]:
        #     async for data in stream:
        #         res_symbol = _from_symbol(data['s'])
        #         if res_symbol != symbol:
        #             continue
        #         status = _from_order_status(data['X'])
        #         if status is OrderStatus.NEW:
        #             yield OrderUpdate.New(
        #                 client_id=data['c'],
        #             )
        #         elif status is OrderStatus.PARTIALLY_FILLED:
        #             yield OrderUpdate.Match(
        #                 client_id=data['c'],
        #                 fill=Fill(
        #                     price=Decimal(data['L']),
        #                     size=Decimal(data['l']),
        #                     quote=Decimal(data['Y']),
        #                     fee=Decimal(data['n']),
        #                     fee_asset=data['N'].lower(),
        #                 ),
        #             )
        #         elif status is OrderStatus.FILLED:
        #             yield OrderUpdate.Match(
        #                 client_id=data['c'],
        #                 fill=Fill(
        #                     price=Decimal(data['L']),
        #                     size=Decimal(data['l']),
        #                     quote=Decimal(data['Y']),
        #                     fee=Decimal(data['n']),
        #                     fee_asset=data['N'].lower(),
        #                 ),
        #             )
        #             yield OrderUpdate.Done(
        #                 time=data['T'],  # Transaction time.
        #                 client_id=data['c'],
        #             )
        #         elif status is OrderStatus.CANCELLED:
        #             # 'c' is client order id, 'C' is original client order id. 'C' is usually empty
        #             # except for when an order gets cancelled; in that case 'c' has a new value.
        #             yield OrderUpdate.Cancelled(
        #                 time=data['T'],
        #                 client_id=data['C'],
        #             )
        #         else:
        #             raise NotImplementedError(data)

        # # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#order-update
        # user_data_stream = await self._get_user_data_stream(account)
        # async with user_data_stream.subscribe('executionReport') as stream:
        #     yield inner(stream)

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        assert account == 'spot'
        raise NotImplementedError()
        # result = {}
        # _, content = await self._api_request(
        #     'GET', '/api/v3/account', weight=5, security=_SEC_USER_DATA
        # )
        # result['spot'] = {
        #     b['asset'].lower(): Balance(
        #         available=Decimal(b['free']),
        #         hold=Decimal(b['locked']),
        #     )
        #     for b in content['balances']
        # }
        # return result

    def map_candle_intervals(self) -> dict[int, int]:
        raise NotImplementedError()
        # return {
        #     60000: 0,  # 1m
        #     180000: 0,  # 3m
        #     300000: 0,  # 5m
        #     900000: 0,  # 15m
        #     1800000: 0,  # 30m
        #     3600000: 0,  # 1h
        #     7200000: 0,  # 2h
        #     14400000: 0,  # 4h
        #     21600000: 0,  # 6h
        #     28800000: 0,  # 8h
        #     43200000: 0,  # 12h
        #     86400000: 0,  # 1d
        #     259200000: 0,  # 3d
        #     604800000: 345600000,  # 1w 4d
        #     2629746000: 2541726000,  # 1M 4w1d10h2m6s
        # }

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        raise NotImplementedError()
        # limit = 1000  # Max possible candles per request.
        # binance_interval = strfinterval(interval)
        # binance_symbol = _to_http_symbol(symbol)
        # # Start 0 is a special value indicating that we try to find the earliest available candle.
        # pagination_interval = interval
        # if start == 0:
        #     pagination_interval = end - start
        # for page_start, page_end in page(start, end, pagination_interval, limit):
        #     _, content = await self._api_request(
        #         'GET',
        #         '/api/v3/klines',
        #         data={
        #             'symbol': binance_symbol,
        #             'interval': binance_interval,
        #             'startTime': page_start,
        #             'endTime': page_end - 1,
        #             'limit': limit
        #         }
        #     )
        #     for c in content:
        #         # Binance can return bad candles where the time does not fall within the requested
        #         # interval. For example, the second candle of the following query has bad time:
        #         # https://api.binance.com/api/v1/klines?symbol=ETHBTC&interval=4h&limit=10&startTime=1529971200000&endTime=1530000000000
        #         yield Candle(
        #             c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
        #             Decimal(c[5]), True
        #         )

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        async with self._session.request(method=method, url=_API_URL + url, **kwargs) as response:
            result = await response.json()
        return result


def _from_symbol(symbol: str) -> str:
    return symbol.lower().replace('_', '-')


def _to_symbol(symbol: str) -> str:
    return symbol.upper().replace('-', '_')
