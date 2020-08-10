from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import urllib.parse
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator, Callable, Dict, List, Optional

import aiohttp
from tenacity import (
    before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential
)

from juno import (
    AccountType, Balance, BorrowInfo, Candle, Depth, ExchangeException, ExchangeInfo, Fees, Fill,
    Order, OrderException, OrderResult, OrderStatus, OrderType, OrderUpdate, Side, Ticker,
    TimeInForce, Trade, json
)
from juno.asyncio import Event, cancel, create_task_cancel_on_exc, stream_queue
from juno.filters import Filters, MinNotional, PercentPrice, Price, Size
from juno.http import ClientJsonResponse, ClientSession, connect_refreshing_stream
from juno.itertools import page
from juno.math import ratios, split_by_ratios
from juno.time import DAY_SEC, HOUR_MS, HOUR_SEC, MIN_MS, MIN_SEC, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter, unpack_symbol

from .exchange import Exchange

_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_MARGIN = 5  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_ERR_NEW_ORDER_REJECTED = -2010
_ERR_CANCEL_REJECTED = -2011
_ERR_INVALID_TIMESTAMP = -1021
_ERR_INVALID_LISTEN_KEY = -1125
_ERR_TOO_MANY_REQUESTS = -1003
_ERR_ISOLATED_MARGIN_ACCOUNT_DOES_NOT_EXIST = -11001

_log = logging.getLogger(__name__)


class Binance(Exchange):
    # Capabilities.
    can_stream_balances: bool = True
    can_stream_depth_snapshot: bool = False
    can_stream_historical_candles: bool = True
    can_stream_historical_earliest_candle: bool = True
    can_stream_candles: bool = True
    can_list_all_tickers: bool = True
    can_margin_trade: bool = True
    can_place_order_market_quote: bool = True

    def __init__(self, api_key: str, secret_key: str, high_precision: bool = True) -> None:
        if not high_precision:
            _log.warning('high precision updates disabled')

        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')
        self._high_precision = high_precision

        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)

        # Rate limiters.
        x = 1.5  # We use this factor to be on the safe side and not use up the entire bucket.
        self._reqs_per_min_limiter = AsyncLimiter(1200, 60 * x)
        self._raw_reqs_limiter = AsyncLimiter(5000, 300 * x)
        self._orders_per_sec_limiter = AsyncLimiter(10, 1 * x)
        self._orders_per_day_limiter = AsyncLimiter(100_000, DAY_SEC * x)
        self._margin_limiter = AsyncLimiter(1, 2 * x)

        self._clock = Clock(self)
        self._user_data_streams: Dict[str, UserDataStream] = {}

    async def __aenter__(self) -> Binance:
        await self._session.__aenter__()
        await self._clock.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            # self._isolated_margin_user_data_stream.__aexit__(exc_type, exc, tb),
            # self._cross_margin_user_data_stream.__aexit__(exc_type, exc, tb),
            # self._spot_user_data_stream.__aexit__(exc_type, exc, tb),
            *(s.__aexit__(exc_type, exc, tb) for s in self._user_data_streams.values()),
            self._clock.__aexit__(exc_type, exc, tb),
        )
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/wapi-api.md#trade-fee-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#exchange-information
        fees_res, filters_res = await asyncio.gather(
            self._wapi_request('GET', '/wapi/v3/tradeFee.html', security=_SEC_USER_DATA),
            self._api_request('GET', '/api/v3/exchangeInfo'),
        )
        fees = {
            _from_symbol(fee['symbol']):
            Fees(maker=Decimal(fee['maker']), taker=Decimal(fee['taker']))
            for fee in fees_res.data['tradeFee']
        }
        filters = {}
        for symbol in filters_res.data['symbols']:
            for f in symbol['filters']:
                t = f['filterType']
                if t == 'PRICE_FILTER':
                    price = f
                elif t == 'PERCENT_PRICE':
                    percent_price = f
                elif t == 'LOT_SIZE':
                    lot_size = f
                elif t == 'MIN_NOTIONAL':
                    min_notional = f
            assert all((price, percent_price, lot_size, min_notional))

            filters[f"{symbol['baseAsset'].lower()}-{symbol['quoteAsset'].lower()}"] = Filters(
                price=Price(
                    min=Decimal(price['minPrice']),
                    max=Decimal(price['maxPrice']),
                    step=Decimal(price['tickSize'])
                ),
                percent_price=PercentPrice(
                    multiplier_up=Decimal(percent_price['multiplierUp']),
                    multiplier_down=Decimal(percent_price['multiplierDown']),
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                ),
                size=Size(
                    min=Decimal(lot_size['minQty']),
                    max=Decimal(lot_size['maxQty']),
                    step=Decimal(lot_size['stepSize'])
                ),
                min_notional=MinNotional(
                    min_notional=Decimal(min_notional['minNotional']),
                    apply_to_market=min_notional['applyToMarket'],
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                ),
                base_precision=symbol['baseAssetPrecision'],
                quote_precision=symbol['quoteAssetPrecision'],
                is_spot_trading_allowed='SPOT' in symbol['permissions'],
                is_margin_trading_allowed='MARGIN' in symbol['permissions'],
            )
        return ExchangeInfo(
            fees=fees,
            filters=filters,
            # 1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M
            candle_intervals=[
                60000, 180000, 300000, 900000, 1800000, 3600000, 7200000, 14400000, 21600000,
                28800000, 43200000, 86400000, 259200000, 604800000, 2629746000
            ],
            # The data below is not available through official Binance API but fetched through
            # "binance_fetch_borrow_info.py" script.
            # Last updated on 2020-07-09.
            borrow_info={
                'matic': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('1E+5')),
                'vet': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('6E+6')),
                'usdt': BorrowInfo(daily_interest_rate=Decimal('0.000325'), limit=Decimal('8E+5')),
                'rvn': BorrowInfo(daily_interest_rate=Decimal('0.0001'), limit=Decimal('5E+4')),
                'dash': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('2E+2')),
                'atom': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('3.5E+3')),
                'ont': BorrowInfo(daily_interest_rate=Decimal('0.0003'), limit=Decimal('1.6E+4')),
                'xrp': BorrowInfo(daily_interest_rate=Decimal('0.0001'), limit=Decimal('2E+5')),
                'xlm': BorrowInfo(daily_interest_rate=Decimal('0.0001'), limit=Decimal('2.5E+5')),
                'link': BorrowInfo(
                    daily_interest_rate=Decimal('0.00025'), limit=Decimal('1.5E+4')
                ),
                'trx': BorrowInfo(daily_interest_rate=Decimal('0.000225'), limit=Decimal('2E+6')),
                'qtum': BorrowInfo(daily_interest_rate=Decimal('0.0001'), limit=Decimal('4E+3')),
                'xtz': BorrowInfo(daily_interest_rate=Decimal('0.0001'), limit=Decimal('4E+3')),
                'iost': BorrowInfo(daily_interest_rate=Decimal('0.0003'), limit=Decimal('2E+6')),
                'bch': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('2E+2')),
                'eos': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('1.5E+4')),
                'btc': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('6E+1')),
                'iota': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('2E+4')),
                'bat': BorrowInfo(daily_interest_rate=Decimal('0.0003'), limit=Decimal('3.5E+4')),
                'etc': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('4E+3')),
                'bnb': BorrowInfo(daily_interest_rate=Decimal('0.003'), limit=Decimal('3E+3')),
                'eth': BorrowInfo(
                    daily_interest_rate=Decimal('0.000275'), limit=Decimal('1.2E+3')
                ),
                'neo': BorrowInfo(daily_interest_rate=Decimal('0.0003'), limit=Decimal('1.8E+3')),
                'zec': BorrowInfo(daily_interest_rate=Decimal('0.0003'), limit=Decimal('2.5E+2')),
                'ltc': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('9E+2')),
                'usdc': BorrowInfo(daily_interest_rate=Decimal('0.000325'), limit=Decimal('4E+5')),
                'busd': BorrowInfo(daily_interest_rate=Decimal('0.000325'), limit=Decimal('4E+5')),
                'xmr': BorrowInfo(daily_interest_rate=Decimal('0.0002'), limit=Decimal('3E+2')),
                'ada': BorrowInfo(daily_interest_rate=Decimal('0.0004'), limit=Decimal('5E+5')),
            },
            # TODO: The multiplier differs per symbol and whether we use cross or isolated margin.
            # margin_multiplier=3,
            margin_multiplier=2,
        )

    async def list_tickers(self, symbols: List[str] = []) -> List[Ticker]:
        if len(symbols) > 1:
            raise NotImplementedError()

        data = {'symbol': _to_http_symbol(symbols[0])} if symbols else None
        weight = 1 if symbols else 40
        res = await self._api_request('GET', '/api/v3/ticker/24hr', data=data, weight=weight)
        response_data = [res.data] if symbols else res.data
        return [
            Ticker(
                symbol=_from_symbol(t['symbol']),
                volume=Decimal(t['volume']),
                quote_volume=Decimal(t['quoteVolume'])
            ) for t in response_data
        ]

    async def map_balances(self, margin: bool = False) -> Dict[str, Balance]:
        url = '/sapi/v1/margin/account' if margin else '/api/v3/account'
        weight = 1 if margin else 5
        res = await self._api_request('GET', url, weight=weight, security=_SEC_USER_DATA)
        return {
            b['asset'].lower(): Balance(
                available=Decimal(b['free']),
                hold=Decimal(b['locked']),
                borrowed=Decimal(b['borrowed'] if margin else Decimal('0.0')),
                interest=Decimal(b['interest'] if margin else Decimal('0.0')),
            )
            for b in res.data['userAssets' if margin else 'balances']
        }

    async def map_isolated_margin_balances(self) -> Dict[str, Dict[str, Balance]]:
        url = '/sapi/v1/margin/isolated/account'
        res = await self._api_request('GET', url, weight=1, security=_SEC_USER_DATA)
        result = {}
        for balances in res.data['assets']:
            symbol = _from_symbol(balances['symbol'])
            base_asset, quote_asset = unpack_symbol(symbol)
            base_balance = balances['baseAsset']
            quote_balance = balances['quoteAsset']
            result[symbol] = {
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
        return result

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: AccountType = AccountType.SPOT, isolated_symbol: Optional[str] = None
    ) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        async def inner(
            stream: AsyncIterable[Dict[str, Any]]
        ) -> AsyncIterable[Dict[str, Balance]]:
            async for data in stream:
                result = {}
                for balance in data['B']:
                    result[
                        balance['a'].lower()
                    ] = Balance(available=Decimal(balance['f']), hold=Decimal(balance['l']))
                yield result

        # 'outboundAccountInfo' - Full list of balances.
        # 'outboundAccountPosition' - Only changed balances.
        user_data_stream = await self._get_user_data_stream(account, isolated_symbol)
        async with user_data_stream.subscribe('outboundAccountPosition') as stream:
            yield inner(stream)

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # TODO: We might wanna increase that and accept higher weight.
        LIMIT = 100
        LIMIT_TO_WEIGHT = {
            5: 1,
            10: 1,
            20: 1,
            50: 1,
            100: 1,
            500: 5,
            1000: 10,
            5000: 50,
        }
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#market-data-endpoints
        res = await self._api_request(
            'GET',
            '/api/v3/depth',
            weight=LIMIT_TO_WEIGHT[LIMIT],
            data={
                'limit': LIMIT,
                'symbol': _to_http_symbol(symbol)
            }
        )
        return Depth.Snapshot(
            bids=[(Decimal(x[0]), Decimal(x[1])) for x in res.data['bids']],
            asks=[(Decimal(x[0]), Decimal(x[1])) for x in res.data['asks']],
            last_id=res.data['lastUpdateId'],
        )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for data in ws:
                yield Depth.Update(
                    bids=[(Decimal(m[0]), Decimal(m[1])) for m in data['b']],
                    asks=[(Decimal(m[0]), Decimal(m[1])) for m in data['a']],
                    first_id=data['U'],
                    last_id=data['u']
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        url = f'/ws/{_to_ws_symbol(symbol)}@depth'
        if self._high_precision:  # Low precision is every 1000ms.
            url += '@100ms'
        async with self._connect_refreshing_stream(
            url=url, interval=12 * HOUR_SEC, name='depth', raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    async def list_orders(self, symbol: Optional[str], margin: bool = False) -> List[Order]:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#current-open-orders-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/margin-api.md#query-margin-accounts-open-order-user_data
        url = '/sapi/v1/margin/openOrders' if margin else '/api/v3/openOrders'
        # For margin:
        # > When all symbols are returned, the number of requests counted against the rate limiter
        # > is equal to the number of symbols currently trading on the exchange.
        # TODO: Make the margin no-symbol weight calc dynamic.
        weight = (10 if symbol else 29) if margin else (1 if symbol else 40)
        data = {}
        if symbol is not None:
            data['symbol'] = _to_http_symbol(symbol)
        res = await self._api_request(
            'GET',
            url,
            data=data,
            security=_SEC_USER_DATA,
            weight=weight,
        )
        return [
            Order(
                client_id=o['clientOrderId'],
                symbol=_from_symbol(o['symbol']),
                price=Decimal(o['price']),
                size=Decimal(o['origQty']),
            ) for o in res.data
        ]

    @asynccontextmanager
    async def connect_stream_orders(
        self, symbol: str, account: AccountType = AccountType.SPOT,
        isolated_symbol: Optional[str] = None
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        async def inner(stream: AsyncIterable[Dict[str, Any]]) -> AsyncIterable[OrderUpdate.Any]:
            async for data in stream:
                res_symbol = _from_symbol(data['s'])
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
                elif status is OrderStatus.CANCELED:
                    # 'c' is client order id, 'C' is original client order id. 'C' is usually empty
                    # except for when an order gets cancelled; in that case 'c' has a new value.
                    yield OrderUpdate.Canceled(
                        time=data['T'],
                        client_id=data['C'],
                    )
                else:
                    raise NotImplementedError(data)

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#order-update
        user_data_stream = await self._get_user_data_stream(account, isolated_symbol)
        async with user_data_stream.subscribe('executionReport') as stream:
            yield inner(stream)

    async def place_order(
        self,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
        account: AccountType = AccountType.SPOT,
        test: bool = True,
    ) -> OrderResult:
        if test and account.is_margin:
            raise ValueError('Binance does not support placing test orders on margin accounts')

        data: Dict[str, Any] = {
            'symbol': _to_http_symbol(symbol),
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
        if account is AccountType.ISOLATED_MARGIN:
            data['isIsolated'] = 'TRUE'
        url = '/sapi/v1/margin/order' if account.is_margin else '/api/v3/order'
        if test:
            url += '/test'
        res = await self._api_request('POST', url, data=data, security=_SEC_TRADE)
        if test:
            return OrderResult(time=time_ms(), status=OrderStatus.NEW)
        total_size = Decimal(res.data['executedQty'])
        total_quote = Decimal(res.data['cummulativeQuoteQty'])
        fill_quotes = split_by_ratios(
            total_quote,
            ratios(total_size, [Decimal(f['qty']) for f in res.data['fills']]),
        )
        return OrderResult(
            time=res.data['transactTime'],
            status=_from_order_status(res.data['status']),
            fills=[
                Fill(
                    price=Decimal(f['price']),
                    size=Decimal(f['qty']),
                    quote=q,
                    fee=Decimal(f['commission']),
                    fee_asset=f['commissionAsset'].lower()
                ) for f, q in zip(res.data['fills'], fill_quotes)
            ]
        )

    async def cancel_order(
        self,
        symbol: str,
        client_id: str,
        account: AccountType = AccountType.SPOT,
    ) -> None:
        url = '/sapi/v1/margin/order' if account.is_margin else '/api/v3/order'
        data = {'symbol': _to_http_symbol(symbol), 'origClientOrderId': client_id}
        await self._api_request('DELETE', url, data=data, security=_SEC_TRADE)

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        limit = 1000  # Max possible candles per request.
        # Start 0 is a special value indicating that we try to find the earliest available candle.
        pagination_interval = interval
        if start == 0:
            pagination_interval = end - start
        for page_start, page_end in page(start, end, pagination_interval, limit):
            res = await self._api_request(
                'GET',
                '/api/v3/klines',
                data={
                    'symbol': _to_http_symbol(symbol),
                    'interval': strfinterval(interval),
                    'startTime': page_start,
                    'endTime': page_end - 1,
                    'limit': limit
                }
            )
            for c in res.data:
                yield Candle(
                    c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                    Decimal(c[5]), True
                )

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for data in ws:
                c = data['k']
                yield Candle(
                    c['t'], Decimal(c['o']), Decimal(c['h']), Decimal(c['l']), Decimal(c['c']),
                    Decimal(c['v']), c['x']
                )

        async with self._connect_refreshing_stream(
            url=f'/ws/{_to_ws_symbol(symbol)}@kline_{strfinterval(interval)}',
            interval=12 * HOUR_SEC,
            name='candles',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        # Aggregated trades. This means trades executed at the same time, same price and as part of
        # the same order will be aggregated by summing their size.
        batch_start = start
        payload: Dict[str, Any] = {
            'symbol': _to_http_symbol(symbol),
        }
        while True:
            batch_end = batch_start + HOUR_MS
            payload['startTime'] = batch_start
            payload['endTime'] = min(batch_end, end) - 1  # Inclusive.

            time = None

            res = await self._api_request('GET', '/api/v3/aggTrades', data=payload)
            for t in res.data:
                time = t['T']
                assert time < end
                yield Trade(
                    id=t['a'],
                    time=time,
                    price=Decimal(t['p']),
                    size=Decimal(t['q']),
                )
            batch_start = time + 1 if time is not None else batch_end
            if batch_start >= end:
                break

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for data in ws:
                yield Trade(
                    id=data['a'],
                    time=data['T'],
                    price=Decimal(data['p']),
                    size=Decimal(data['q']),
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#trade-streams
        async with self._connect_refreshing_stream(
            url=f'/ws/{_to_ws_symbol(symbol)}@trade', interval=12 * HOUR_SEC, name='trade',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    async def transfer(self, asset: str, size: Decimal, margin: bool) -> None:
        await self._api_request(
            'POST',
            '/sapi/v1/margin/transfer',
            data={
                'asset': _to_asset(asset),
                'amount': _to_decimal(size),
                'type': 1 if margin else 2,
            },
            security=_SEC_MARGIN,
        )

    async def transfer_isolated(
        self, asset: str, symbol: str, from_margin: bool, to_margin: bool, size: Decimal
    ) -> None:
        await self._api_request(
            'POST',
            '/sapi/v1/margin/isolated/transfer',
            data={
                'asset': _to_asset(asset),
                'symbol': _to_http_symbol(symbol),
                'transFrom': 'ISOLATED_MARGIN' if from_margin else 'SPOT',
                'transTo': 'ISOLATED_MARGIN' if to_margin else 'SPOT',
                'amount': _to_decimal(size),
            },
            security=_SEC_MARGIN,
        )

    async def borrow(
        self, asset: str, size: Decimal, isolated: bool = False,
        isolated_symbol: Optional[str] = None
    ) -> None:
        data = {
            'asset': _to_asset(asset),
            'amount': _to_decimal(size),
        }
        if isolated:
            data['isIsolated'] = 'TRUE'
        if isolated_symbol is not None:
            data['symbol'] = _to_http_symbol(isolated_symbol)
        await self._api_request(
            'POST',
            '/sapi/v1/margin/loan',
            data=data,
            security=_SEC_MARGIN,
        )

    async def repay(
        self, asset: str, size: Decimal, isolated: bool = False,
        isolated_symbol: Optional[str] = None
    ) -> None:
        data = {
            'asset': _to_asset(asset),
            'amount': _to_decimal(size),
        }
        if isolated:
            data['isIsolated'] = 'TRUE'
        if isolated_symbol is not None:
            data['symbol'] = _to_http_symbol(isolated_symbol)
        await self._api_request(
            'POST',
            '/sapi/v1/margin/repay',
            data=data,
            security=_SEC_MARGIN,
        )

    async def get_max_borrowable(
        self, asset: str, isolated_symbol: Optional[str] = None
    ) -> Decimal:
        data = {'asset': _to_asset(asset)}
        if isolated_symbol is not None:
            data['isolatedSymbol'] = isolated_symbol
        res = await self._api_request(
            'GET',
            '/sapi/v1/margin/maxBorrowable',
            data=data,
            security=_SEC_USER_DATA,
            weight=5,
        )
        return Decimal(res.data['amount'])

    async def get_max_transferable(
        self, asset: str, isolated_symbol: Optional[str] = None
    ) -> Decimal:
        data = {'asset': _to_asset(asset)}
        if isolated_symbol is not None:
            data['isolatedSymbol'] = isolated_symbol
        res = await self._api_request(
            'GET',
            '/sapi/v1/margin/maxTransferable ',
            data=data,
            security=_SEC_USER_DATA,
            weight=5,
        )
        return Decimal(res.data['amount'])

    async def create_isolated_margin_account(self, symbol: str) -> None:
        base_asset, quote_asset = unpack_symbol(symbol)
        await self._api_request(
            'POST',
            '/sapi/v1/margin/isolated/create',
            data={
                'base': _to_asset(base_asset),
                'quote': _to_asset(quote_asset),
            },
            security=_SEC_USER_DATA,
        )

    async def _wapi_request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
    ) -> Any:
        res = await self._request(
            method=method,
            url=url,
            weight=weight,
            data=data,
            security=security,
        )
        if not res.data['success']:
            # There's no error code in this response to figure out whether it's a timestamp issue.
            # We could look it up from the message, but currently just assume that is the case
            # always.
            _log.warning(f'received error: {res.data["msg"]}; syncing clock before exc')
            self._clock.clear()
            raise ExchangeException(res.data['msg'])
        res.raise_for_status()
        return res

    async def _api_request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
    ) -> Any:
        res = await self._request(
            method=method,
            url=url,
            weight=weight,
            data=data,
            security=security,
        )
        if isinstance(res.data, dict):
            if (error_code := res.data.get('code')) is not None:
                error_msg = res.data.get('msg')
                _log.warning(
                    f'received http status {res.status}; code {error_code}; msg {error_msg}'
                )
                if error_code == _ERR_INVALID_TIMESTAMP:
                    _log.warning('received invalid timestamp; syncing clock before exc')
                    self._clock.clear()
                    raise ExchangeException(error_msg)
                elif error_code == _ERR_INVALID_LISTEN_KEY:
                    # TODO: If status 50X (502 for example during exchange maintenance), we may
                    # want to wait for a some kind of a successful health check before retrying.
                    raise ExchangeException(error_msg)
                elif error_code == _ERR_CANCEL_REJECTED:
                    raise OrderException(error_msg)
                elif error_code == _ERR_NEW_ORDER_REJECTED:
                    raise OrderException(error_msg)
                elif error_code == _ERR_ISOLATED_MARGIN_ACCOUNT_DOES_NOT_EXIST:
                    # TODO: Ugly!
                    return res
                # TODO: Check only specific error codes.
                elif error_code <= -9000:  # Filter error.
                    raise OrderException(error_msg)
                elif error_code == -1013:  # TODO: Not documented but also a filter error O_o
                    raise OrderException(error_msg)
                elif error_code == _ERR_TOO_MANY_REQUESTS:
                    if (retry_after := res.headers.get('Retry-After')):
                        _log.info(f'server provided retry-after {retry_after}; sleeping')
                        await asyncio.sleep(float(retry_after))
                    raise ExchangeException(error_msg)
                else:
                    raise NotImplementedError(f'No handling for binance error: {res.data}')
        res.raise_for_status()
        return res

    async def _request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
    ) -> ClientJsonResponse:
        limiters = [
            self._raw_reqs_limiter.acquire(),
            self._reqs_per_min_limiter.acquire(weight),
        ]
        if url in ['/api/v3/order', '/sapi/v1/margin/order']:
            limiters.extend((
                self._orders_per_day_limiter.acquire(),
                self._orders_per_sec_limiter.acquire(),
            ))
        elif url in ['/sapi/v1/margin/transfer', '/sapi/v1/margin/loan', '/sapi/v1/margin/repay']:
            limiters.append(self._margin_limiter.acquire())

        await asyncio.gather(*limiters)

        kwargs: Dict[str, Any] = {}

        if security in [
            _SEC_TRADE, _SEC_USER_DATA, _SEC_MARGIN, _SEC_USER_STREAM, _SEC_MARKET_DATA
        ]:
            kwargs['headers'] = {'X-MBX-APIKEY': self._api_key}

        if security in [_SEC_TRADE, _SEC_USER_DATA, _SEC_MARGIN]:
            await self._clock.wait()

            data = data or {}
            data['timestamp'] = time_ms() + self._clock.time_diff
            query_str_bytes = urllib.parse.urlencode(data).encode('utf-8')
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data['signature'] = signature.hexdigest()

        if data:
            kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request_json(
            method=method, url=_BASE_REST_URL + url, **kwargs
        ) as res:
            return res

    @asynccontextmanager
    async def _connect_refreshing_stream(
        self, url: str, interval: int, name: str, raise_on_disconnect: bool = False
    ) -> AsyncIterator[AsyncIterable[Any]]:
        try:
            async with connect_refreshing_stream(
                self._session,
                url=_BASE_WS_URL + url,
                interval=interval,
                loads=json.loads,
                take_until=lambda old, new: old['E'] < new['E'],
                name=name,
                raise_on_disconnect=raise_on_disconnect
            ) as stream:
                yield stream
        except aiohttp.WebSocketError as e:
            _log.warning(f'{name} web socket exc: {e}')
            raise ExchangeException(str(e))

    async def _get_user_data_stream(
        self, account: AccountType, isolated_symbol: Optional[str]
    ) -> UserDataStream:
        if account is AccountType.SPOT:
            return await self._get_or_create_user_data_stream(
                '__spot__', lambda: UserDataStream(self, '/api/v3/userDataStream')
            )
        if account is AccountType.CROSS_MARGIN:
            return await self._get_or_create_user_data_stream(
                '__cross_margin__', lambda: UserDataStream(self, '/sapi/v1/userDataStream')
            )
        if account is AccountType.ISOLATED_MARGIN:
            if not isolated_symbol:
                raise ValueError('Isolated symbol is required for isolated margin account')
            return await self._get_or_create_user_data_stream(
                isolated_symbol,
                lambda: UserDataStream(self, '/sapi/v1/userDataStream/isolated', isolated_symbol),
            )
        raise NotImplementedError()

    async def _get_or_create_user_data_stream(
        self, key: str, factory: Callable[[], UserDataStream]
    ) -> UserDataStream:
        if not (stream := self._user_data_streams.get(key)):
            stream = factory()
            self._user_data_streams[key] = stream
            await stream.__aenter__()
        return stream


class Clock:
    def __init__(self, binance: Binance) -> None:
        self.time_diff = 0
        self._binance = binance
        self._synced = asyncio.Event()
        self._periodic_sync_task: Optional[asyncio.Task[None]] = None
        self._reset_periodic_sync: Event[None] = Event(autoclear=True)

    async def __aenter__(self) -> Clock:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._periodic_sync_task)

    async def wait(self) -> None:
        if not self._periodic_sync_task:
            self._periodic_sync_task = create_task_cancel_on_exc(self._periodic_sync())

        await self._synced.wait()

    def clear(self) -> None:
        self._synced.clear()
        if self._periodic_sync_task:
            self._reset_periodic_sync.set()

    async def _periodic_sync(self) -> None:
        while True:
            await self._sync_clock()
            sleep_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(HOUR_SEC * 12))
            try:
                await asyncio.wait(
                    [sleep_task, self._reset_periodic_sync.wait()],
                    return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                if not sleep_task.done():
                    with suppress(asyncio.CancelledError):
                        await cancel(sleep_task)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _sync_clock(self) -> None:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#check-server-time
        _log.info('syncing clock with Binance')
        before = time_ms()
        server_time = (await self._binance._api_request('GET', '/api/v3/time')).data['serverTime']
        after = time_ms()
        # Assume response time is same as request time.
        delay = (after - before) // 2
        local_time = before + delay
        # Adjustment required converting from local time to server time.
        self.time_diff = server_time - local_time
        _log.info(f'found {self.time_diff}ms time difference')
        self._synced.set()


class UserDataStream:
    def __init__(self, binance: Binance, base_url: str, symbol: Optional[str] = None) -> None:
        self._binance = binance
        self._base_url = base_url
        self._symbol = symbol
        self._listen_key_lock = asyncio.Lock()
        self._stream_connected = asyncio.Event()
        self._listen_key = None

        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None
        self._old_tasks: List[asyncio.Task[None]] = []

        self._queues: Dict[str, Dict[str, asyncio.Queue]] = (
            defaultdict(lambda: defaultdict(asyncio.Queue))
        )

    async def __aenter__(self) -> UserDataStream:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        # We could delete a listen key here but we don't. Listen key is scoped to account and we
        # don't want to delete listen keys for other juno instances tied to the same account.
        # It will get deleted automatically by Binance after 60 mins of inactivity.
        # if self._listen_key:
        #     await self._delete_listen_key(self._listen_key)
        await cancel(self._listen_key_refresh_task, self._stream_user_data_task)

    @asynccontextmanager
    async def subscribe(self, event_type: str) -> AsyncIterator[AsyncIterable[Any]]:
        # TODO: Note that someone else might consume the event data while we do the initial
        # fetch request. This might require a more sophisticated tracking impl.
        # For example, instead of pub/sub events, keep a queue of messages and deliver them
        # based on timestamps.
        await self._ensure_connection()
        try:
            event_queues = self._queues[event_type]
            queue_id = str(uuid.uuid4())
            yield stream_queue(event_queues[queue_id], raise_on_exc=True)
        finally:
            del event_queues[queue_id]
            # TODO: unsubscribe if no other consumers?

    async def _ensure_listen_key(self) -> None:
        async with self._listen_key_lock:
            if not self._listen_key:
                response = await self._create_listen_key()
                if (
                    response.status == 400
                    and response.data['code'] == _ERR_ISOLATED_MARGIN_ACCOUNT_DOES_NOT_EXIST
                ):
                    _log.warning(
                        f'isolated margin account does not exist for {self._symbol}; '
                        'creating and retrying'
                    )
                    assert self._symbol
                    await self._binance.create_isolated_margin_account(self._symbol)
                    response = await self._create_listen_key()
                self._listen_key = response.data['listenKey']

    async def _ensure_connection(self) -> None:
        await self._ensure_listen_key()

        if not self._listen_key_refresh_task:
            self._listen_key_refresh_task = create_task_cancel_on_exc(
                self._periodic_listen_key_refresh()
            )

        if not self._stream_user_data_task:
            self._stream_user_data_task = create_task_cancel_on_exc(
                self._stream_user_data()
            )

        await self._stream_connected.wait()

    async def _periodic_listen_key_refresh(self) -> None:
        while True:
            await asyncio.sleep(30 * MIN_SEC)
            if self._listen_key:
                try:
                    await self._update_listen_key(self._listen_key)
                except ExchangeException:
                    _log.warning(f'tried to update a listen key {self._listen_key} which did not '
                                 'exist; resetting')
                    self._listen_key = None
                    await self._ensure_listen_key()
            else:
                _log.warning('want to refresh listen key but missing locally')

    async def _stream_user_data(self) -> None:
        while True:
            try:
                async with self._binance._connect_refreshing_stream(
                    url=f'/ws/{self._listen_key}', interval=12 * HOUR_SEC, name='user',
                    raise_on_disconnect=True
                ) as stream:
                    self._stream_connected.set()
                    async for data in stream:
                        event_queues = self._queues[data['e']]
                        for queue in event_queues.values():
                            queue.put_nowait(data)
                break
            except ExchangeException as e:
                for event_queues in self._queues.values():
                    for queue in event_queues.values():
                        queue.put_nowait(e)
            await self._ensure_listen_key()

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _create_listen_key(self) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#create-a-listenkey
        data = {}
        if self._symbol is not None:
            data['symbol'] = _to_http_symbol(self._symbol)
        return await self._binance._api_request(
            'POST',
            self._base_url,
            data=data,
            security=_SEC_USER_STREAM
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _update_listen_key(self, listen_key: str) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        data = {}
        if self._symbol is not None:
            data['symbol'] = _to_http_symbol(self._symbol)
        return await self._binance._api_request(
            'PUT',
            self._base_url,
            data={'listenKey': listen_key},
            security=_SEC_USER_STREAM,
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _delete_listen_key(self, listen_key: str) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
        data = {}
        if self._symbol is not None:
            data['symbol'] = _to_http_symbol(self._symbol)
        return await self._binance._api_request(
            'DELETE',
            self._base_url,
            data={'listenKey': listen_key},
            security=_SEC_USER_STREAM
        )


def _to_asset(asset: str) -> str:
    return asset.upper()


def _to_http_symbol(symbol: str) -> str:
    return symbol.replace('-', '').upper()


def _to_ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '')


def _from_symbol(symbol: str) -> str:
    # TODO: May be incorrect! We can't systematically know which part is base and which is quote
    # since there is no separator used. We simply map based on known quote assets.
    known_quote_assets = [
        'BNB', 'BTC', 'ETH', 'XRP', 'USDT', 'PAX', 'TUSD', 'USDC', 'USDS', 'TRX', 'BUSD', 'NGN',
        'RUB', 'TRY', 'EUR', 'ZAR', 'BKRW', 'IDRT', 'GBP', 'UAH', 'BIDR', 'AUD'
    ]
    for asset in known_quote_assets:
        if symbol.endswith(asset):
            base = symbol[:-len(asset)]
            quote = asset
            break
    else:
        _log.warning(f'unknown quote asset found in symbol: {symbol}')
        # We round up because usually base asset is the longer one (i.e IOTABTC).
        split_index = math.ceil(len(symbol) / 2)
        base = symbol[:split_index]
        quote = symbol[split_index:]
    return f'{base.lower()}-{quote.lower()}'


def _to_side(side: Side) -> str:
    return {
        Side.BUY: 'BUY',
        Side.SELL: 'SELL',
    }[side]


def _to_order_type(type_: OrderType) -> str:
    return {
        OrderType.MARKET: 'MARKET',
        OrderType.LIMIT: 'LIMIT',
        OrderType.STOP_LOSS: 'STOP_LOSS',
        OrderType.STOP_LOSS_LIMIT: 'STOP_LOSS_LIMIT',
        OrderType.TAKE_PROFIT: 'TAKE_PROFIT',
        OrderType.TAKE_PROFIT_LIMIT: 'TAKE_PROFIT_LIMIT',
        OrderType.LIMIT_MAKER: 'LIMIT_MAKER',
    }[type_]


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    return {
        TimeInForce.GTC: 'GTC',
        TimeInForce.IOC: 'IOC',
        TimeInForce.FOK: 'FOK',
        TimeInForce.GTT: 'GTT',
    }[time_in_force]


def _from_order_status(status: str) -> OrderStatus:
    status_map = {
        'NEW': OrderStatus.NEW,
        'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
        'FILLED': OrderStatus.FILLED,
        'CANCELED': OrderStatus.CANCELED
    }
    mapped_status = status_map.get(status)
    if not mapped_status:
        raise NotImplementedError(f'Handling of status {status} not implemented')
    return mapped_status


def _to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f'{value:f}'
