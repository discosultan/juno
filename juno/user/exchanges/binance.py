from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator, Optional

from multidict import MultiDict

from juno import (
    Balance,
    Fill,
    Order,
    OrderMissing,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    OrderWouldBeTaker,
    Side,
    TimeInForce,
)
from juno.exchanges.binance import Session, from_http_symbol, to_asset, to_http_symbol
from juno.itertools import page
from juno.time import DAY_MS, DAY_SEC, strptimestamp, time_ms
from juno.user.exchanges import Exchange
from juno.utils import AsyncLimiter, unpack_assets

_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_MARGIN = 5  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_ERR_UNKNOWN = -1000
_ERR_NEW_ORDER_REJECTED = -2010
_ERR_MARGIN_NEW_ORDER_REJECTED = 27037
_ERR_CANCEL_REJECTED = -2011
_ERR_INVALID_TIMESTAMP = -1021
_ERR_INVALID_LISTEN_KEY = -1125
_ERR_TOO_MANY_REQUESTS = -1003
_ERR_ISOLATED_MARGIN_ACCOUNT_DOES_NOT_EXIST = -11001
_ERR_ISOLATED_MARGIN_ACCOUNT_EXISTS = -11004

_BINANCE_START = strptimestamp('2017-07-01')

_log = logging.getLogger(__name__)


class Binance(Exchange):
    # Capabilities.
    can_stream_balances: bool = True
    can_margin_trade: bool = True
    can_place_market_order: bool = True
    can_place_market_order_quote: bool = True

    def __init__(self, session: Session) -> None:
        self._session = session

        # Rate limiters.
        x = 1.5  # We use this factor to be on the safe side and not use up the entire bucket.
        self._reqs_per_min_limiter = AsyncLimiter(1200, 60 * x)
        self._raw_reqs_limiter = AsyncLimiter(5000, 300 * x)
        self._orders_per_sec_limiter = AsyncLimiter(10, 1 * x)
        self._orders_per_day_limiter = AsyncLimiter(100_000, DAY_SEC * x)
        self._margin_limiter = AsyncLimiter(1, 2 * x)

        self._user_data_streams: dict[str, UserDataStream] = {}

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        result = {}
        if account == 'spot':
            _, content = await self._session.api_request(
                'GET', '/api/v3/account', weight=10, security=_SEC_USER_DATA
            )
            result['spot'] = {
                b['asset'].lower(): Balance(
                    available=Decimal(b['free']),
                    hold=Decimal(b['locked']),
                )
                for b in content['balances']
            }
        elif account == 'margin':
            _, content = await self._session.api_request(
                'GET', '/sapi/v1/margin/account', weight=1, security=_SEC_USER_DATA
            )
            result['margin'] = {
                b['asset'].lower(): Balance(
                    available=Decimal(b['free']),
                    hold=Decimal(b['locked']),
                    borrowed=Decimal(b['borrowed']),
                    interest=Decimal(b['interest']),
                )
                for b in content['userAssets']
            }
        elif account == 'isolated':
            # TODO: Binance also accepts a symbols param here to return only up to 5 account info.
            # The weight is the same though, so not much benefit to using that.
            # https://binance-docs.github.io/apidocs/spot/en/#query-isolated-margin-account-info-user_data
            _, content = await self._api_request(
                'GET', '/sapi/v1/margin/isolated/account', weight=1, security=_SEC_USER_DATA
            )
            for balances in content['assets']:
                base_asset, quote_asset = unpack_assets(from_http_symbol(balances['symbol']))
                base_balance = balances['baseAsset']
                quote_balance = balances['quoteAsset']
                result[f'{base_asset}-{quote_asset}'] = {
                    base_asset: Balance(
                        available=Decimal(base_balance['free']),
                        hold=Decimal(base_balance['locked']),
                        borrowed=Decimal(base_balance['borrowed']),
                        interest=Decimal(base_balance['interest']),
                    ),
                    quote_asset: Balance(
                        available=Decimal(quote_balance['free']),
                        hold=Decimal(quote_balance['locked']),
                        borrowed=Decimal(quote_balance['borrowed']),
                        interest=Decimal(quote_balance['interest']),
                    ),
                }
        else:
            raise NotImplementedError()
        return result

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        async def inner(
            stream: AsyncIterable[dict[str, Any]]
        ) -> AsyncIterable[dict[str, Balance]]:
            async for data in stream:
                result = {}
                for balance in data['B']:
                    result[
                        balance['a'].lower()
                    ] = Balance(available=Decimal(balance['f']), hold=Decimal(balance['l']))
                yield result

        # Yields only assets that are possibly changed.
        user_data_stream = await self._get_user_data_stream(account)
        async with user_data_stream.subscribe('outboundAccountPosition') as stream:
            yield inner(stream)

    async def list_orders(self, account: str, symbol: Optional[str] = None) -> list[Order]:
        if account not in ['spot', 'margin']:
            if symbol is None:
                symbol = account
            elif symbol != account:
                raise ValueError(f'Invalid isolated margin symbol {symbol} for account {account}')

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#current-open-orders-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/margin-api.md#query-margin-accounts-open-order-user_data
        # https://binance-docs.github.io/apidocs/spot/en/#query-margin-account-39-s-order-user_data
        url = '/api/v3/openOrders' if account == 'spot' else '/sapi/v1/margin/openOrders'
        # For margin:
        # > When all symbols are returned, the number of requests counted against the rate limiter
        # > is equal to the number of symbols currently trading on the exchange.
        # TODO: For margin accounts, if symbol specified, the weight in GitHub docs states 10 but
        # in binance-docs 1. Clarify!
        # TODO: Make the margin no-symbol weight calc dynamic.
        weight = (3 if symbol else 40) if account == 'spot' else (10 if symbol else 40)
        data = {}
        if symbol is not None:
            data['symbol'] = to_http_symbol(symbol)
        if account not in ['spot', 'margin']:
            data['isIsolated'] = 'TRUE'
        _, content = await self._session.api_request(
            'GET',
            url,
            data=data,
            security=_SEC_USER_DATA,
            weight=weight,
        )
        return [
            Order(
                client_id=o['clientOrderId'],
                symbol=from_http_symbol(o['symbol']),
                price=Decimal(o['price']),
                size=Decimal(o['origQty']),
            ) for o in content
        ]

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        async def inner(stream: AsyncIterable[dict[str, Any]]) -> AsyncIterable[OrderUpdate.Any]:
            async for data in stream:
                res_symbol = from_http_symbol(data['s'])
                if res_symbol != symbol:
                    continue
                status = _from_order_status(data['X'])
                if status is OrderStatus.NEW:
                    yield OrderUpdate.New(
                        client_id=data['c'],
                    )
                elif status is OrderStatus.PARTIALLY_FILLED:
                    yield OrderUpdate.Match(
                        client_id=data['c'],
                        fill=Fill(
                            price=Decimal(data['L']),
                            size=Decimal(data['l']),
                            quote=Decimal(data['Y']),
                            fee=Decimal(data['n']),
                            fee_asset=data['N'].lower(),
                        ),
                    )
                elif status is OrderStatus.FILLED:
                    yield OrderUpdate.Match(
                        client_id=data['c'],
                        fill=Fill(
                            price=Decimal(data['L']),
                            size=Decimal(data['l']),
                            quote=Decimal(data['Y']),
                            fee=Decimal(data['n']),
                            fee_asset=data['N'].lower(),
                        ),
                    )
                    yield OrderUpdate.Done(
                        time=data['T'],  # Transaction time.
                        client_id=data['c'],
                    )
                elif status is OrderStatus.CANCELLED:
                    # 'c' is client order id, 'C' is original client order id. 'C' is usually empty
                    # except for when an order gets cancelled; in that case 'c' has a new value.
                    yield OrderUpdate.Cancelled(
                        time=data['T'],
                        client_id=data['C'],
                    )
                else:
                    raise NotImplementedError(data)

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#order-update
        user_data_stream = await self._get_user_data_stream(account)
        async with user_data_stream.subscribe('executionReport') as stream:
            yield inner(stream)

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
        data: dict[str, Any] = {
            'symbol': to_http_symbol(symbol),
            'side': _to_side(side),
            'type': _to_order_type(type_),
        }
        if size is not None:
            data['quantity'] = _to_decimal(size)
        if quote is not None:
            data['quoteOrderQty'] = _to_decimal(quote)
        if price is not None:
            data['price'] = _to_decimal(price)
        if time_in_force is not None:
            data['timeInForce'] = _to_time_in_force(time_in_force)
        if client_id is not None:
            data['newClientOrderId'] = client_id
        if account not in ['spot', 'margin']:
            data['isIsolated'] = 'TRUE'
        if account == 'spot':
            url = '/api/v3/order'
            weight = 2
        else:
            url = '/sapi/v1/margin/order'
            weight = 1
        _, content = await self._session.api_request(
            'POST', url, data=data, security=_SEC_TRADE, weight=weight
        )

        # In case of LIMIT_MARKET order, the following are not present in the response:
        # - status
        # - cummulativeQuoteQty
        # - fills
        total_quote = Decimal(q) if (q := content.get('cummulativeQuoteQty')) else Decimal('0.0')
        return OrderResult(
            time=content['transactTime'],
            status=(
                _from_order_status(status) if (status := content.get('status'))
                else OrderStatus.NEW
            ),
            fills=[
                Fill(
                    price=(p := Decimal(f['price'])),
                    size=(s := Decimal(f['qty'])),
                    quote=(p * s).quantize(total_quote),
                    fee=Decimal(f['commission']),
                    fee_asset=f['commissionAsset'].lower()
                ) for f in content.get('fills', [])
            ]
        )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        url = '/api/v3/order' if account == 'spot' else '/sapi/v1/margin/order'
        data = {
            'symbol': to_http_symbol(symbol),
            'origClientOrderId': client_id,
        }
        if account not in ['spot', 'margin']:
            data['isIsolated'] = 'TRUE'
        await self._session.api_request('DELETE', url, data=data, security=_SEC_TRADE)

    async def transfer(
        self, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        if from_account in ['spot', 'margin'] and to_account in ['spot', 'margin']:
            assert from_account != to_account
            await self._session.api_request(
                'POST',
                '/sapi/v1/margin/transfer',
                data={
                    'asset': to_asset(asset),
                    'amount': _to_decimal(size),
                    'type': 1 if to_account == 'margin' else 2,
                },
                security=_SEC_MARGIN,
            )
        else:
            assert from_account != 'margin' and to_account != 'margin'
            assert from_account == 'spot' or to_account == 'spot'
            to_spot = to_account == 'spot'
            await self._session.api_request(
                'POST',
                '/sapi/v1/margin/isolated/transfer',
                data={
                    'asset': to_asset(asset),
                    'symbol': to_http_symbol(from_account if to_spot else to_account),
                    'transFrom': 'ISOLATED_MARGIN' if to_spot else 'SPOT',
                    'transTo': 'SPOT' if to_spot else 'ISOLATED_MARGIN',
                    'amount': _to_decimal(size),
                },
                security=_SEC_MARGIN,
            )

    async def borrow(self, asset: str, size: Decimal, account) -> None:
        assert account != 'spot'
        data = {
            'asset': to_asset(asset),
            'amount': _to_decimal(size),
        }
        if account != 'margin':
            data['isIsolated'] = 'TRUE'
            data['symbol'] = to_http_symbol(account)
        await self._session.api_request(
            'POST',
            '/sapi/v1/margin/loan',
            data=data,
            security=_SEC_MARGIN,
        )

    async def repay(self, asset: str, size: Decimal, account: str) -> None:
        assert account != 'spot'
        data = {
            'asset': to_asset(asset),
            'amount': _to_decimal(size),
        }
        if account != 'margin':
            data['isIsolated'] = 'TRUE'
            data['symbol'] = to_http_symbol(account)
        await self._session.api_request(
            'POST',
            '/sapi/v1/margin/repay',
            data=data,
            security=_SEC_MARGIN,
        )

    async def get_max_borrowable(self, asset: str, account: str) -> Decimal:
        assert account != 'spot'
        data = {'asset': to_asset(asset)}
        if account != 'margin':
            data['isolatedSymbol'] = to_http_symbol(account)
        _, content = await self._session.api_request(
            'GET',
            '/sapi/v1/margin/maxBorrowable',
            data=data,
            security=_SEC_USER_DATA,
            weight=5,
        )
        return Decimal(content['amount'])

    async def get_max_transferable(self, asset: str, account: str) -> Decimal:
        assert account != 'spot'
        data = {'asset': to_asset(asset)}
        if account != 'margin':
            data['isolatedSymbol'] = to_http_symbol(account)
        _, content = await self._session.api_request(
            'GET',
            '/sapi/v1/margin/maxTransferable',
            data=data,
            security=_SEC_USER_DATA,
            weight=5,
        )
        return Decimal(content['amount'])

    async def create_account(self, account: str) -> None:
        assert account not in ['spot', 'margin']
        base_asset, quote_asset = unpack_assets(account)
        await self._session.api_request(
            'POST',
            '/sapi/v1/margin/isolated/create',
            data={
                'base': to_asset(base_asset),
                'quote': to_asset(quote_asset),
            },
            security=_SEC_USER_DATA,
        )

    async def convert_dust(self, assets: list[str]) -> None:
        await self._session.api_request(
            'POST',
            '/sapi/v1/asset/dust',
            data=MultiDict([('asset', to_asset(a)) for a in assets]),
            security=_SEC_USER_DATA,
        )

    async def _list_symbols(self, isolated: bool = False) -> list[str]:
        _, content = await self._session.api_request(
            'GET',
            f'/sapi/v1/margin{"/isolated" if isolated else ""}/allPairs',
            security=_SEC_USER_DATA,
        )
        return [from_http_symbol(s['symbol']) for s in content]

    async def list_open_accounts(self) -> list[str]:
        _, content = await self._session.api_request(
            'GET', '/sapi/v1/margin/isolated/account', security=_SEC_USER_DATA
        )
        return ['spot', 'margin'] + [from_http_symbol(b['symbol']) for b in content['assets']]

    async def list_deposit_history(self, end: Optional[int] = None):
        # Does not support FIAT.
        end = time_ms() if end is None else end
        tasks = []
        for page_start, page_end in page(_BINANCE_START, end, DAY_MS * 90):
            tasks.append(self._session.api_request(
                'GET',
                '/sapi/v1/capital/deposit/hisrec',
                data={
                    'startTime': page_start,
                    'endTime': page_end - 1,
                },
                security=_SEC_USER_DATA,
            ))
        results = await asyncio.gather(*tasks)
        return [record for _, content in results for record in content]

    async def list_withdraw_history(self, end: Optional[int] = None):
        # Does not support FIAT.
        end = time_ms() if end is None else end
        tasks = []
        for page_start, page_end in page(_BINANCE_START, end, DAY_MS * 90):
            tasks.append(self._session.api_request(
                'GET',
                '/sapi/v1/capital/withdraw/history',
                data={
                    'startTime': page_start,
                    'endTime': page_end - 1,
                },
                security=_SEC_USER_DATA,
            ))
        results = await asyncio.gather(*tasks)
        return [record for _, content in results for record in content]

    async def _get_user_data_stream(self, account: str) -> UserDataStream:
        if not (stream := self._user_data_streams.get(account)):
            stream = UserDataStream(self, account)
            self._user_data_streams[account] = stream
            await stream.__aenter__()
        return stream


def _to_side(side: Side) -> str:
    return {
        Side.BUY: 'BUY',
        Side.SELL: 'SELL',
    }[side]


def _to_order_type(type_: OrderType) -> str:
    return {
        OrderType.MARKET: 'MARKET',
        OrderType.LIMIT: 'LIMIT',
        # OrderType.STOP_LOSS: 'STOP_LOSS',
        # OrderType.STOP_LOSS_LIMIT: 'STOP_LOSS_LIMIT',
        # OrderType.TAKE_PROFIT: 'TAKE_PROFIT',
        # OrderType.TAKE_PROFIT_LIMIT: 'TAKE_PROFIT_LIMIT',
        OrderType.LIMIT_MAKER: 'LIMIT_MAKER',
    }[type_]


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    return {
        TimeInForce.GTC: 'GTC',
        TimeInForce.IOC: 'IOC',
        TimeInForce.FOK: 'FOK',
        # TimeInForce.GTT: 'GTT',
    }[time_in_force]


def _from_order_status(status: str) -> OrderStatus:
    status_map = {
        'NEW': OrderStatus.NEW,
        'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
        'FILLED': OrderStatus.FILLED,
        'CANCELED': OrderStatus.CANCELLED
    }
    mapped_status = status_map.get(status)
    if not mapped_status:
        raise NotImplementedError(f'Handling of status {status} not implemented')
    return mapped_status


def _to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f'{value:f}'
