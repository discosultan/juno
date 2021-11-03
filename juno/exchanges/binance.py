from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import urllib.parse
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator, Optional, TypedDict

import aiohttp
from multidict import MultiDict
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from juno import (
    AssetInfo,
    BadOrder,
    Balance,
    BorrowInfo,
    Candle,
    Depth,
    ExchangeException,
    ExchangeInfo,
    Fees,
    Fill,
    Order,
    OrderMissing,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    OrderWouldBeTaker,
    SavingsProduct,
    Side,
    Ticker,
    TimeInForce,
    Trade,
    json,
)
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, stream_queue
from juno.filters import Filters, MinNotional, PercentPrice, Price, Size
from juno.http import ClientResponse, ClientSession, connect_refreshing_stream
from juno.itertools import page, page_limit
from juno.time import (
    DAY_MS,
    DAY_SEC,
    HOUR_MS,
    HOUR_SEC,
    MIN_MS,
    MIN_SEC,
    strfinterval,
    strptimestamp,
    time_ms,
)
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter, unpack_assets

from .exchange import Exchange

_BASE_API_URL = "https://api.binance.com"
_BASE_WS_URL = "wss://stream.binance.com:9443"
_BASE_GATEWAY_URL = "https://www.binance.com/gateway-api"

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
_ERR_SYSTEM_BUSY = -3044
_ERR_DAILY_REDEEM_AMOUNT_ERROR = -6006
_ERR_DAILY_REDEEM_TIME_ERROR = -6007
_ERR_REQUEST_FREQUENCY_TOO_HIGH = -6009

_LIMITERS_BASIC = 1
_LIMITERS_ORDER = 2
_LIMITERS_ONCE_PER_SEC = 3

_BINANCE_START = strptimestamp("2017-07-01")

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
    can_place_market_order: bool = True
    can_place_market_order_quote: bool = True

    def __init__(self, api_key: str, secret_key: str, high_precision: bool = True) -> None:
        if not high_precision:
            _log.warning("high precision updates disabled")

        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode("utf-8")
        self._high_precision = high_precision

        self._session = ClientSession(
            raise_for_status=False,
            name=type(self).__name__,
            # Optionally, if we don't want to handle ServerDisconnectedError due to keep-alive
            # expiring, we can set this header. We will lose some perf tho, because a new SSL
            # handshake is performed for every request.
            # https://github.com/aio-libs/aiohttp/issues/850
            # headers={'Connection': 'close'},
        )

        # Rate limiters.
        x = 1.5  # We use this factor to be on the safe side and not use up the entire bucket.
        self._reqs_per_min_limiter = AsyncLimiter(1200, 60 * x)
        self._raw_reqs_limiter = AsyncLimiter(5000, 300 * x)
        self._orders_per_sec_limiter = AsyncLimiter(10, 1 * x)
        self._orders_per_day_limiter = AsyncLimiter(100_000, DAY_SEC * x)
        self._once_per_sec_limiters: dict[str, AsyncLimiter] = defaultdict(
            lambda: AsyncLimiter(1, 1 * x)
        )

        self._clock = Clock(self)
        self._user_data_streams: dict[str, UserDataStream] = {}

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

    def list_candle_intervals(self) -> list[int]:
        return [
            60000,  # 1m
            180000,  # 3m
            300000,  # 5m
            900000,  # 15m
            1800000,  # 30m
            3600000,  # 1h
            7200000,  # 2h
            14400000,  # 4h
            21600000,  # 6h
            28800000,  # 8h
            43200000,  # 12h
            86400000,  # 1d
            259200000,  # 3d
            604800000,  # 1w
            2629746000,  # 1M
        ]

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/wapi-api.md#trade-fee-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#exchange-information
        fees_res, filters_res, isolated_pairs, margin_res, isolated_res = await asyncio.gather(
            self._api_request_json(
                method="GET",
                url="/sapi/v1/asset/tradeFee",
                security=_SEC_USER_DATA,
            ),
            self._api_request_json(
                method="GET",
                url="/api/v3/exchangeInfo",
                weight=10,
            ),
            self._list_symbols(isolated=True),
            self._gateway_request_json(
                method="GET",
                url="/v1/friendly/margin/vip/spec/list-all",
            ),
            self._gateway_request_json(
                method="GET",
                url="/v1/public/isolated-margin/pair/vip-level",
            ),
        )

        # Process fees.
        fees = {
            _from_symbol(fee["symbol"]): Fees(
                maker=Decimal(fee["makerCommission"]), taker=Decimal(fee["takerCommission"])
            )
            for fee in fees_res
        }

        # Process borrow info.
        # The data below is not available through official Binance API. We can get borrow limit but
        # there is no way to get interest rate.
        borrow_info = {
            "margin": {
                a["assetName"].lower(): BorrowInfo(
                    daily_interest_rate=Decimal(s["dailyInterestRate"]),
                    limit=Decimal(s["borrowLimit"]),
                )
                for a, s in ((a, a["specs"][0]) for a in margin_res["data"])
            },
        }
        for p in isolated_res["data"]:
            base = p["base"]
            base_asset = base["assetName"].lower()
            quote = p["quote"]
            quote_asset = quote["assetName"].lower()

            base_levels = base["levelDetails"]
            if len(base_levels) == 0:
                _log.info(
                    f"no isolated margin borrow info for {base_asset}-{quote_asset} "
                    f"{base_asset} asset"
                )
                continue
            base_details = base_levels[0]

            quote_levels = quote["levelDetails"]
            if len(quote_levels) == 0:
                _log.info(
                    f"no isolated margin borrow info for {base_asset}-{quote_asset} "
                    f"{quote_asset} asset"
                )
                continue
            quote_details = quote_levels[0]

            borrow_info[f"{base_asset}-{quote_asset}"] = {
                base_asset: BorrowInfo(
                    daily_interest_rate=Decimal(base_details["interestRate"]),
                    limit=Decimal(base_details["maxBorrowable"]),
                ),
                quote_asset: BorrowInfo(
                    daily_interest_rate=Decimal(quote_details["interestRate"]),
                    limit=Decimal(quote_details["maxBorrowable"]),
                ),
            }

        # Process symbol info.
        isolated_pairs_set = set(isolated_pairs)
        filters = {}
        for symbol_info in filters_res["symbols"]:
            for f in symbol_info["filters"]:
                t = f["filterType"]
                if t == "PRICE_FILTER":
                    price = f
                elif t == "PERCENT_PRICE":
                    percent_price = f
                elif t == "LOT_SIZE":
                    lot_size = f
                elif t == "MIN_NOTIONAL":
                    min_notional = f
            assert all((price, percent_price, lot_size, min_notional))

            symbol = f"{symbol_info['baseAsset'].lower()}-{symbol_info['quoteAsset'].lower()}"
            filters[symbol] = Filters(
                price=Price(
                    min=Decimal(price["minPrice"]),
                    max=Decimal(price["maxPrice"]),
                    step=Decimal(price["tickSize"]),
                ),
                percent_price=PercentPrice(
                    multiplier_up=Decimal(percent_price["multiplierUp"]),
                    multiplier_down=Decimal(percent_price["multiplierDown"]),
                    avg_price_period=percent_price["avgPriceMins"] * MIN_MS,
                ),
                size=Size(
                    min=Decimal(lot_size["minQty"]),
                    max=Decimal(lot_size["maxQty"]),
                    step=Decimal(lot_size["stepSize"]),
                ),
                min_notional=MinNotional(
                    min_notional=Decimal(min_notional["minNotional"]),
                    apply_to_market=min_notional["applyToMarket"],
                    avg_price_period=percent_price["avgPriceMins"] * MIN_MS,
                ),
                base_precision=symbol_info["baseAssetPrecision"],
                quote_precision=symbol_info["quoteAssetPrecision"],
                spot="SPOT" in symbol_info["permissions"],
                cross_margin="MARGIN" in symbol_info["permissions"],
                isolated_margin=(symbol in isolated_pairs_set) and (symbol in borrow_info),
            )

        return ExchangeInfo(
            assets={"__all__": AssetInfo(precision=8)},
            fees=fees,
            filters=filters,
            borrow_info=borrow_info,
        )

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        if len(symbols) > 1:
            raise NotImplementedError()

        data = {"symbol": _to_http_symbol(symbols[0])} if symbols else None
        weight = 1 if symbols else 40
        content = await self._api_request_json(
            method="GET",
            url="/api/v3/ticker/24hr",
            data=data,
            weight=weight,
        )
        response_data = [content] if symbols else content
        return {
            _from_symbol(t["symbol"]): Ticker(
                volume=Decimal(t["volume"]),
                quote_volume=Decimal(t["quoteVolume"]),
                price=Decimal(t["lastPrice"]),
            )
            for t in response_data
        }

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        result = {}
        if account == "spot":
            content = await self._api_request_json(
                method="GET",
                url="/api/v3/account",
                weight=10,
                security=_SEC_USER_DATA,
            )
            result["spot"] = {
                b["asset"].lower(): Balance(
                    available=Decimal(b["free"]),
                    hold=Decimal(b["locked"]),
                )
                for b in content["balances"]
            }
        elif account == "margin":
            content = await self._api_request_json(
                method="GET",
                url="/sapi/v1/margin/account",
                security=_SEC_USER_DATA,
            )
            result["margin"] = {
                b["asset"].lower(): Balance(
                    available=Decimal(b["free"]),
                    hold=Decimal(b["locked"]),
                    borrowed=Decimal(b["borrowed"]),
                    interest=Decimal(b["interest"]),
                )
                for b in content["userAssets"]
            }
        elif account == "isolated":
            # TODO: Binance also accepts a symbols param here to return only up to 5 account info.
            # The weight is the same though, so not much benefit to using that.
            # https://binance-docs.github.io/apidocs/spot/en/#query-isolated-margin-account-info-user_data
            content = await self._api_request_json(
                method="GET",
                url="/sapi/v1/margin/isolated/account",
                security=_SEC_USER_DATA,
            )
            for balances in content["assets"]:
                base_asset, quote_asset = unpack_assets(_from_symbol(balances["symbol"]))
                base_balance = balances["baseAsset"]
                quote_balance = balances["quoteAsset"]
                result[f"{base_asset}-{quote_asset}"] = {
                    base_asset: Balance(
                        available=Decimal(base_balance["free"]),
                        hold=Decimal(base_balance["locked"]),
                        borrowed=Decimal(base_balance["borrowed"]),
                        interest=Decimal(base_balance["interest"]),
                    ),
                    quote_asset: Balance(
                        available=Decimal(quote_balance["free"]),
                        hold=Decimal(quote_balance["locked"]),
                        borrowed=Decimal(quote_balance["borrowed"]),
                        interest=Decimal(quote_balance["interest"]),
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
                for balance in data["B"]:
                    result[balance["a"].lower()] = Balance(
                        available=Decimal(balance["f"]), hold=Decimal(balance["l"])
                    )
                yield result

        # Yields only assets that are possibly changed.
        user_data_stream = await self._get_user_data_stream(account)
        async with user_data_stream.subscribe("outboundAccountPosition") as stream:
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
        content = await self._api_request_json(
            method="GET",
            url="/api/v3/depth",
            weight=LIMIT_TO_WEIGHT[LIMIT],
            data={"limit": LIMIT, "symbol": _to_http_symbol(symbol)},
        )
        return Depth.Snapshot(
            bids=[(Decimal(x[0]), Decimal(x[1])) for x in content["bids"]],
            asks=[(Decimal(x[0]), Decimal(x[1])) for x in content["asks"]],
            last_id=content["lastUpdateId"],
        )

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for data in ws:
                yield Depth.Update(
                    bids=[(Decimal(m[0]), Decimal(m[1])) for m in data["b"]],
                    asks=[(Decimal(m[0]), Decimal(m[1])) for m in data["a"]],
                    first_id=data["U"],
                    last_id=data["u"],
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        url = f"/ws/{_to_ws_symbol(symbol)}@depth"
        if self._high_precision:  # Low precision is every 1000ms.
            url += "@100ms"
        async with self._connect_refreshing_stream(
            url=url,
            interval=12 * HOUR_SEC,
            name="depth",
            raise_on_disconnect=True,
        ) as ws:
            yield inner(ws)

    async def list_orders(self, account: str, symbol: Optional[str] = None) -> list[Order]:
        if account not in ["spot", "margin"]:
            if symbol is None:
                symbol = account
            elif symbol != account:
                raise ValueError(f"Invalid isolated margin symbol {symbol} for account {account}")

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#current-open-orders-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/margin-api.md#query-margin-accounts-open-order-user_data
        # https://binance-docs.github.io/apidocs/spot/en/#query-margin-account-39-s-order-user_data
        url = "/api/v3/openOrders" if account == "spot" else "/sapi/v1/margin/openOrders"
        # For margin:
        # > When all symbols are returned, the number of requests counted against the rate limiter
        # > is equal to the number of symbols currently trading on the exchange.
        # TODO: For margin accounts, if symbol specified, the weight in GitHub docs states 10 but
        # in binance-docs 1. Clarify!
        # TODO: Make the margin no-symbol weight calc dynamic.
        weight = (3 if symbol else 40) if account == "spot" else (10 if symbol else 40)
        data = {}
        if symbol is not None:
            data["symbol"] = _to_http_symbol(symbol)
        if account not in ["spot", "margin"]:
            data["isIsolated"] = "TRUE"
        content = await self._api_request_json(
            method="GET",
            url=url,
            data=data,
            weight=weight,
            security=_SEC_USER_DATA,
        )
        return [
            Order(
                client_id=o["clientOrderId"],
                symbol=_from_symbol(o["symbol"]),
                price=Decimal(o["price"]),
                size=Decimal(o["origQty"]),
            )
            for o in content
        ]

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        async def inner(stream: AsyncIterable[dict[str, Any]]) -> AsyncIterable[OrderUpdate.Any]:
            async for data in stream:
                res_symbol = _from_symbol(data["s"])
                if res_symbol != symbol:
                    continue
                status = _from_order_status(data["X"])
                if status is OrderStatus.NEW:
                    yield OrderUpdate.New(
                        client_id=data["c"],
                    )
                elif status is OrderStatus.PARTIALLY_FILLED:
                    yield OrderUpdate.Match(
                        client_id=data["c"],
                        fill=Fill(
                            price=Decimal(data["L"]),
                            size=Decimal(data["l"]),
                            quote=Decimal(data["Y"]),
                            fee=Decimal(data["n"]),
                            fee_asset=data["N"].lower(),
                        ),
                    )
                elif status is OrderStatus.FILLED:
                    yield OrderUpdate.Match(
                        client_id=data["c"],
                        fill=Fill(
                            price=Decimal(data["L"]),
                            size=Decimal(data["l"]),
                            quote=Decimal(data["Y"]),
                            fee=Decimal(data["n"]),
                            fee_asset=data["N"].lower(),
                        ),
                    )
                    yield OrderUpdate.Done(
                        time=data["T"],  # Transaction time.
                        client_id=data["c"],
                    )
                elif status is OrderStatus.CANCELLED:
                    # 'c' is client order id, 'C' is original client order id. 'C' is usually empty
                    # except for when an order gets cancelled; in that case 'c' has a new value.
                    yield OrderUpdate.Cancelled(
                        time=data["T"],
                        client_id=data["C"],
                    )
                else:
                    raise NotImplementedError(data)

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#order-update
        user_data_stream = await self._get_user_data_stream(account)
        async with user_data_stream.subscribe("executionReport") as stream:
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
            "symbol": _to_http_symbol(symbol),
            "side": _to_side(side),
            "type": _to_order_type(type_),
        }
        if size is not None:
            data["quantity"] = _to_decimal(size)
        if quote is not None:
            data["quoteOrderQty"] = _to_decimal(quote)
        if price is not None:
            data["price"] = _to_decimal(price)
        if time_in_force is not None:
            data["timeInForce"] = _to_time_in_force(time_in_force)
        if client_id is not None:
            data["newClientOrderId"] = client_id
        if account not in ["spot", "margin"]:
            data["isIsolated"] = "TRUE"
        if account == "spot":
            url = "/api/v3/order"
            weight = 2
        else:
            url = "/sapi/v1/margin/order"
            weight = 1
        content = await self._api_request_json(
            method="POST",
            url=url,
            data=data,
            weight=weight,
            limiters=_LIMITERS_ORDER,
            security=_SEC_TRADE,
        )

        # In case of LIMIT_MARKET order, the following are not present in the response:
        # - status
        # - cummulativeQuoteQty
        # - fills
        total_quote = Decimal(q) if (q := content.get("cummulativeQuoteQty")) else Decimal("0.0")
        return OrderResult(
            time=content["transactTime"],
            status=(
                _from_order_status(status)
                if (status := content.get("status"))
                else OrderStatus.NEW
            ),
            fills=[
                Fill(
                    price=(p := Decimal(f["price"])),
                    size=(s := Decimal(f["qty"])),
                    quote=(p * s).quantize(total_quote),
                    fee=Decimal(f["commission"]),
                    fee_asset=f["commissionAsset"].lower(),
                )
                for f in content.get("fills", [])
            ],
        )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        url = "/api/v3/order" if account == "spot" else "/sapi/v1/margin/order"
        data = {
            "symbol": _to_http_symbol(symbol),
            "origClientOrderId": client_id,
        }
        if account not in ["spot", "margin"]:
            data["isIsolated"] = "TRUE"
        await self._api_request_json(
            method="DELETE",
            url=url,
            data=data,
            limiters=_LIMITERS_ORDER,
            security=_SEC_TRADE,
        )

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        limit = 1000  # Max possible candles per request.
        binance_interval = strfinterval(interval)
        binance_symbol = _to_http_symbol(symbol)
        # Start 0 is a special value indicating that we try to find the earliest available candle.
        pagination_interval = interval
        if start == 0:
            pagination_interval = end - start
        for page_start, page_end in page_limit(start, end, pagination_interval, limit):
            content = await self._api_request_json(
                method="GET",
                url="/api/v3/klines",
                data={
                    "symbol": binance_symbol,
                    "interval": binance_interval,
                    "startTime": page_start,
                    "endTime": page_end - 1,
                    "limit": limit,
                },
            )
            for c in content:
                # Binance can return bad candles where the time does not fall within the requested
                # interval. For example, the second candle of the following query has bad time:
                # https://api.binance.com/api/v3/klines?symbol=ETHBTC&interval=4h&limit=10&startTime=1529971200000&endTime=1530000000000
                yield Candle(
                    c[0],
                    Decimal(c[1]),
                    Decimal(c[2]),
                    Decimal(c[3]),
                    Decimal(c[4]),
                    Decimal(c[5]),
                    True,
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
                c = data["k"]
                yield Candle(
                    c["t"],
                    Decimal(c["o"]),
                    Decimal(c["h"]),
                    Decimal(c["l"]),
                    Decimal(c["c"]),
                    Decimal(c["v"]),
                    c["x"],
                )

        async with self._connect_refreshing_stream(
            url=f"/ws/{_to_ws_symbol(symbol)}@kline_{strfinterval(interval)}",
            interval=12 * HOUR_SEC,
            name="candles",
            raise_on_disconnect=True,
        ) as ws:
            yield inner(ws)

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        # Aggregated trades. This means trades executed at the same time, same price and as part of
        # the same order will be aggregated by summing their size.
        batch_start = start
        payload: dict[str, Any] = {
            "symbol": _to_http_symbol(symbol),
        }
        while True:
            batch_end = batch_start + HOUR_MS
            payload["startTime"] = batch_start
            payload["endTime"] = min(batch_end, end) - 1  # Inclusive.

            time = None

            content = await self._api_request_json(
                method="GET",
                url="/api/v3/aggTrades",
                data=payload,
            )
            for t in content:
                time = t["T"]
                assert time < end
                yield Trade(
                    id=t["a"],
                    time=time,
                    price=Decimal(t["p"]),
                    size=Decimal(t["q"]),
                )
            batch_start = time + 1 if time is not None else batch_end
            if batch_start >= end:
                break

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for data in ws:
                yield Trade(
                    id=data["a"],
                    time=data["T"],
                    price=Decimal(data["p"]),
                    size=Decimal(data["q"]),
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#trade-streams
        async with self._connect_refreshing_stream(
            url=f"/ws/{_to_ws_symbol(symbol)}@trade",
            interval=12 * HOUR_SEC,
            name="trade",
            raise_on_disconnect=True,
        ) as ws:
            yield inner(ws)

    async def transfer(
        self, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        if from_account in ["spot", "margin"] and to_account in ["spot", "margin"]:
            assert from_account != to_account
            await self._api_request_json(
                method="POST",
                url="/sapi/v1/margin/transfer",
                data={
                    "asset": _to_asset(asset),
                    "amount": _to_decimal(size),
                    "type": 1 if to_account == "margin" else 2,
                },
                security=_SEC_MARGIN,
            )
        else:
            assert from_account != "margin" and to_account != "margin"
            assert from_account == "spot" or to_account == "spot"
            to_spot = to_account == "spot"
            await self._api_request_json(
                method="POST",
                url="/sapi/v1/margin/isolated/transfer",
                data={
                    "asset": _to_asset(asset),
                    "symbol": _to_http_symbol(from_account if to_spot else to_account),
                    "transFrom": "ISOLATED_MARGIN" if to_spot else "SPOT",
                    "transTo": "SPOT" if to_spot else "ISOLATED_MARGIN",
                    "amount": _to_decimal(size),
                },
                security=_SEC_MARGIN,
            )

    async def borrow(self, asset: str, size: Decimal, account) -> None:
        assert account != "spot"
        data = {
            "asset": _to_asset(asset),
            "amount": _to_decimal(size),
        }
        if account != "margin":
            data["isIsolated"] = "TRUE"
            data["symbol"] = _to_http_symbol(account)
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/margin/loan",
            data=data,
            limiters=_LIMITERS_ONCE_PER_SEC,  # Not documented.
            security=_SEC_MARGIN,
        )

    async def repay(self, asset: str, size: Decimal, account: str) -> None:
        assert account != "spot"
        data = {
            "asset": _to_asset(asset),
            "amount": _to_decimal(size),
        }
        if account != "margin":
            data["isIsolated"] = "TRUE"
            data["symbol"] = _to_http_symbol(account)
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/margin/repay",
            data=data,
            limiters=_LIMITERS_ONCE_PER_SEC,  # Not documented.
            security=_SEC_MARGIN,
        )

    async def get_max_borrowable(self, asset: str, account: str) -> Decimal:
        assert account != "spot"
        data = {"asset": _to_asset(asset)}
        if account != "margin":
            data["isolatedSymbol"] = _to_http_symbol(account)
        content = await self._api_request_json(
            method="GET",
            url="/sapi/v1/margin/maxBorrowable",
            data=data,
            weight=5,
            security=_SEC_USER_DATA,
        )
        return Decimal(content["amount"])

    async def get_max_transferable(self, asset: str, account: str) -> Decimal:
        assert account != "spot"
        data = {"asset": _to_asset(asset)}
        if account != "margin":
            data["isolatedSymbol"] = _to_http_symbol(account)
        content = await self._api_request_json(
            method="GET",
            url="/sapi/v1/margin/maxTransferable",
            data=data,
            weight=5,
            security=_SEC_USER_DATA,
        )
        return Decimal(content["amount"])

    async def convert_dust(self, assets: list[str]) -> None:
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/asset/dust",
            data=MultiDict([("asset", _to_asset(a)) for a in assets]),
            security=_SEC_USER_DATA,
        )

    async def _list_symbols(self, isolated: bool = False) -> list[str]:
        content = await self._api_request_json(
            method="GET",
            url=f'/sapi/v1/margin{"/isolated" if isolated else ""}/allPairs',
            security=_SEC_USER_DATA,
        )
        return [_from_symbol(s["symbol"]) for s in content]

    async def get_deposit_address(self, asset: str) -> str:
        content = await self._api_request_json(
            method="GET",
            url="/sapi/v1/capital/deposit/address",
            data={"coin": _to_asset(asset)},
            security=_SEC_USER_DATA,
        )
        return content["address"]

    async def withdraw(self, asset: str, address: str, amount: Decimal) -> None:
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/capital/withdraw/apply",
            data={
                "coin": _to_asset(asset),
                "address": address,
                "amount": _to_decimal(amount),
            },
            security=_SEC_USER_DATA,
        )

    async def list_deposit_history(self, end: Optional[int] = None) -> list[Any]:
        # Does not support FIAT.
        end = time_ms() if end is None else end
        tasks = []
        for page_start, page_end in page(_BINANCE_START, end, DAY_MS * 90):
            tasks.append(
                self._api_request_json(
                    method="GET",
                    url="/sapi/v1/capital/deposit/hisrec",
                    data={
                        "startTime": page_start,
                        "endTime": page_end - 1,
                    },
                    security=_SEC_USER_DATA,
                )
            )
        results = await asyncio.gather(*tasks)
        return [record for content in results for record in content]

    async def list_withdraw_history(self, end: Optional[int] = None) -> list[Any]:
        # Does not support FIAT.
        end = time_ms() if end is None else end
        tasks = []
        for page_start, page_end in page(_BINANCE_START, end, DAY_MS * 90):
            tasks.append(
                self._api_request_json(
                    method="GET",
                    url="/sapi/v1/capital/withdraw/history",
                    data={
                        "startTime": page_start,
                        "endTime": page_end - 1,
                    },
                    security=_SEC_USER_DATA,
                )
            )
        results = await asyncio.gather(*tasks)
        return [record for content in results for record in content]

    # Savings.

    async def map_savings_products(self) -> dict[str, SavingsProduct]:
        content = await self._api_request_json(
            method="GET",
            url="/sapi/v1/lending/daily/product/list",
            security=_SEC_USER_DATA,
        )
        result = {}
        for product in content:
            asset = _from_asset(product["asset"])
            result[asset] = SavingsProduct(
                product_id=product["productId"],
                status=product["status"],
                asset=asset,
                can_purchase=product["canPurchase"],
                can_redeem=product["canRedeem"],
                purchased_amount=Decimal(product["purchasedAmount"]),
                min_purchase_amount=Decimal(product["minPurchaseAmount"]),
                limit=Decimal(product["upLimit"]),
            )
        return result

    async def purchase_savings_product(self, product_id: str, size: Decimal) -> None:
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/lending/daily/purchase",
            data={
                "productId": product_id,
                "amount": _to_decimal(size),
            },
            security=_SEC_USER_DATA,
        )

    async def redeem_savings_product(self, product_id: str, size: Decimal) -> None:
        await self._api_request_json(
            method="POST",
            url="/sapi/v1/lending/daily/redeem",
            data={
                "productId": product_id,
                "amount": _to_decimal(size),
                "type": "FAST",  # "FAST" | "NORMAL"
            },
            security=_SEC_USER_DATA,
        )

    async def get_savings_product_position(self, asset: str) -> Any:
        return await self._api_request_json(
            method="GET",
            url="/sapi/v1/lending/daily/token/position",
            data={
                "asset": _to_asset(asset),
            },
            security=_SEC_USER_DATA,
        )

    # Common.

    async def _api_request_json(
        self,
        method: str,
        url: str,
        weight: int = 1,
        limiters: int = _LIMITERS_BASIC,
        security: int = _SEC_NONE,
        data: Optional[Any] = None,
    ) -> Any:
        # Preparation.
        limiter_tasks = [
            self._raw_reqs_limiter.acquire(),
            self._reqs_per_min_limiter.acquire(weight),
        ]
        if limiters == _LIMITERS_ORDER:
            limiter_tasks.extend(
                (self._orders_per_day_limiter.acquire(), self._orders_per_sec_limiter.acquire())
            )
        elif limiters == _LIMITERS_ONCE_PER_SEC:
            limiter_tasks.append(self._once_per_sec_limiters[url].acquire())

        await asyncio.gather(*limiter_tasks)

        kwargs: dict[str, Any] = {}

        if security in [
            _SEC_TRADE,
            _SEC_USER_DATA,
            _SEC_MARGIN,
            _SEC_USER_STREAM,
            _SEC_MARKET_DATA,
        ]:
            kwargs["headers"] = {"X-MBX-APIKEY": self._api_key}

        if security in [_SEC_TRADE, _SEC_USER_DATA, _SEC_MARGIN]:
            await self._clock.wait()

            data = data or {}
            data["timestamp"] = time_ms() + self._clock.time_diff
            query_str_bytes = urllib.parse.urlencode(data).encode("utf-8")
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data["signature"] = signature.hexdigest()

        if data:
            kwargs["params" if method == "GET" else "data"] = data

        # Request.
        response = await self._request(method=method, url=_BASE_API_URL + url, **kwargs)
        content = await response.json()

        # Error handling.
        if isinstance(content, dict) and (error_code := content.get("code")) is not None:
            error_msg = content.get("msg")
            _log.warning(
                f"received http status {response.status}; code {error_code}; msg {error_msg}"
            )
            if error_code in {
                _ERR_INVALID_LISTEN_KEY,
                _ERR_ISOLATED_MARGIN_ACCOUNT_DOES_NOT_EXIST,
                _ERR_ISOLATED_MARGIN_ACCOUNT_EXISTS,
                _ERR_SYSTEM_BUSY,
                _ERR_UNKNOWN,
                _ERR_DAILY_REDEEM_AMOUNT_ERROR,
                _ERR_DAILY_REDEEM_TIME_ERROR,
                _ERR_REQUEST_FREQUENCY_TOO_HIGH,
            }:
                raise ExchangeException(error_msg)
            elif error_code == _ERR_INVALID_TIMESTAMP:
                _log.warning("received invalid timestamp; syncing clock before exc")
                self._clock.clear()
                raise ExchangeException(error_msg)
            elif error_code == _ERR_CANCEL_REJECTED:
                raise OrderMissing(error_msg)
            elif error_code in {_ERR_NEW_ORDER_REJECTED, _ERR_MARGIN_NEW_ORDER_REJECTED}:
                if error_msg == "Order would immediately match and take.":
                    raise OrderWouldBeTaker(error_msg)
                else:
                    # For example: 'Account has insufficient balance for requested action.'
                    raise BadOrder(error_msg)
            # TODO: Check only specific error codes.
            elif error_code <= -9000:  # Filter error.
                raise BadOrder(error_msg)
            elif error_code == -1013:  # TODO: Not documented but also a filter error O_o
                raise BadOrder(error_msg)
            elif error_code == _ERR_TOO_MANY_REQUESTS:
                if retry_after := response.headers.get("Retry-After"):
                    _log.info(f"server provided retry-after {retry_after}; sleeping")
                    await asyncio.sleep(float(retry_after))
                raise ExchangeException(error_msg)
            else:
                raise NotImplementedError(f"No handling for error: {response.status} {content}")

        await ExchangeException.raise_for_status(response)
        return content

    async def _gateway_request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        response = await self._request(method, _BASE_GATEWAY_URL + url, **kwargs)

        await ExchangeException.raise_for_status(response)
        return await response.json()

    # We don't want to retry here because the caller of this method may need to adjust request
    # params on retry.
    async def _request(self, method: str, url: str, **kwargs: Any) -> ClientResponse:
        try:
            async with self._session.request(method=method, url=url, **kwargs) as response:
                # TODO: If status 50X (502 for example during exchange maintenance), we may
                # want to wait for a some kind of a successful health check before retrying.
                if response.status >= 500:
                    content = await response.text()
                    raise ExchangeException(f"Server error {response.status} {content}")
                return response
        except (
            aiohttp.ClientConnectionError,
            aiohttp.ClientPayloadError,
        ) as e:
            _log.warning(f"request exc: {e}")
            raise ExchangeException(str(e))

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
                take_until=lambda old, new: old["E"] < new["E"],
                name=name,
                raise_on_disconnect=raise_on_disconnect,
            ) as stream:
                yield stream
        except (
            aiohttp.ClientConnectionError,
            aiohttp.ClientPayloadError,
            aiohttp.ClientResponseError,
            aiohttp.WebSocketError,
        ) as e:
            _log.warning(f"{name} web socket exc: {e}")
            raise ExchangeException(str(e))

    async def _get_user_data_stream(self, account: str) -> UserDataStream:
        if not (stream := self._user_data_streams.get(account)):
            stream = UserDataStream(self, account)
            self._user_data_streams[account] = stream
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
            self._periodic_sync_task = create_task_sigint_on_exception(self._periodic_sync())

        await self._synced.wait()

    def clear(self) -> None:
        self._synced.clear()
        if self._periodic_sync_task:
            self._reset_periodic_sync.set()

    async def _periodic_sync(self) -> None:
        while True:
            await self._sync_clock()
            sleep_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(HOUR_SEC * 6))
            reset_periodic_sync_task = asyncio.create_task(self._reset_periodic_sync.wait())
            try:
                await asyncio.wait(
                    [sleep_task, reset_periodic_sync_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not sleep_task.done():
                    await cancel(sleep_task)
                if not reset_periodic_sync_task.done():
                    await cancel(reset_periodic_sync_task)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _sync_clock(self) -> None:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#check-server-time
        _log.info("syncing clock with Binance")
        before = time_ms()
        content = await self._binance._api_request_json(
            method="GET",
            url="/api/v3/time",
        )
        server_time = content["serverTime"]
        after = time_ms()
        # Assume response time is same as request time.
        delay = (after - before) // 2
        local_time = before + delay
        # Adjustment required converting from local time to server time.
        self.time_diff = server_time - local_time
        _log.info(f"found {self.time_diff}ms time difference")
        self._synced.set()


class CreateListenKeyResult(TypedDict):
    listenKey: str


class UserDataStream:
    def __init__(self, binance: Binance, account: str = "spot") -> None:
        self._binance = binance
        self._url = {
            "spot": "/api/v3/userDataStream",
            "margin": "/sapi/v1/userDataStream",
        }.get(account, "/sapi/v1/userDataStream/isolated")
        self._account = account
        self._listen_key_lock = asyncio.Lock()
        self._stream_connected = asyncio.Event()
        self._listen_key: Optional[str] = None

        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None

        self._queues: dict[str, dict[str, asyncio.Queue]] = defaultdict(
            lambda: defaultdict(asyncio.Queue)
        )

    async def __aenter__(self) -> UserDataStream:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        # We could delete a listen key here but we don't. Listen key is scoped to account and we
        # don't want to delete listen keys for other juno instances tied to the same account.
        # It will get deleted automatically by Binance after 60 mins of inactivity.
        # if self._listen_key:
        #     await self._delete_listen_key(self._listen_key)
        await self._cancel()

    @asynccontextmanager
    async def subscribe(self, event_type: str) -> AsyncIterator[AsyncIterable[Any]]:
        # TODO: Note that someone else might consume the event data while we do the initial
        # fetch request. This might require a more sophisticated tracking impl.
        # For example, instead of pub/sub events, keep a queue of messages and deliver them
        # based on timestamps.

        queue_id = str(uuid.uuid4())

        _log.info(f"subscribing to {self._account} {event_type} events with queue id {queue_id}")
        await self._ensure_connection()
        event_queues = self._queues[event_type]
        _log.info(f"subscribed to {self._account} {event_type} events with queue id {queue_id}")

        try:
            yield stream_queue(event_queues[queue_id], raise_on_exc=True)
        finally:
            _log.info(
                f"unsubscribing from {self._account} {event_type} events with queue id {queue_id}"
            )
            del event_queues[queue_id]
            if all(len(q) == 0 for q in self._queues.values()):
                _log.info(f"no subscriptions left; closing {self._account} user data stream")
                await self._cancel()
            _log.info(
                f"unsubscribed from {self._account} {event_type} events with queue id {queue_id}"
            )

    async def _cancel(self) -> None:
        to_cancel = [
            self._listen_key_refresh_task,
            self._stream_user_data_task,
        ]
        # Clear the state so we can re-initialize on next subscribe.
        self._listen_key = None
        self._listen_key_refresh_task = None
        self._stream_user_data_task = None
        self._stream_connected.clear()
        await cancel(*to_cancel)

    async def _ensure_listen_key(self) -> None:
        if self._listen_key:
            return
        async with self._listen_key_lock:
            if not self._listen_key:
                content = await self._create_listen_key()
                self._listen_key = content["listenKey"]

    async def _ensure_connection(self) -> None:
        await self._ensure_listen_key()

        if not self._listen_key_refresh_task:
            self._listen_key_refresh_task = create_task_sigint_on_exception(
                self._periodic_listen_key_refresh()
            )

        if not self._stream_user_data_task:
            self._stream_user_data_task = create_task_sigint_on_exception(self._stream_user_data())

        await self._stream_connected.wait()

    async def _periodic_listen_key_refresh(self) -> None:
        while True:
            await asyncio.sleep(30 * MIN_SEC)
            if self._listen_key:
                try:
                    await self._update_listen_key(self._listen_key)
                except ExchangeException:
                    _log.warning(
                        f"tried to update a listen key {self._listen_key} which did not "
                        "exist; resetting"
                    )
                    self._listen_key = None
                    await self._ensure_listen_key()
            else:
                _log.warning("want to refresh listen key but missing locally")

    async def _stream_user_data(self) -> None:
        while True:
            try:
                async with self._binance._connect_refreshing_stream(
                    url=f"/ws/{self._listen_key}",
                    interval=12 * HOUR_SEC,
                    name="user",
                    raise_on_disconnect=True,
                ) as stream:
                    self._stream_connected.set()
                    async for data in stream:
                        event_queues = self._queues[data["e"]]
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
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _create_listen_key(self) -> CreateListenKeyResult:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#create-a-listenkey
        data = {}
        if self._account not in ["spot", "margin"]:
            data["symbol"] = _to_http_symbol(self._account)
        return await self._binance._api_request_json(
            method="POST",
            url=self._url,
            data=data,
            security=_SEC_USER_STREAM,
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _update_listen_key(self, listen_key: str) -> None:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        data = {"listenKey": listen_key}
        if self._account not in ["spot", "margin"]:
            data["symbol"] = _to_http_symbol(self._account)
        await self._binance._api_request_json(
            method="PUT",
            url=self._url,
            data=data,
            security=_SEC_USER_STREAM,
        )

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _delete_listen_key(self, listen_key: str) -> None:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
        data = {"listenKey": listen_key}
        if self._account not in ["spot", "margin"]:
            data["symbol"] = _to_http_symbol(self._account)
        await self._binance._api_request_json(
            method="DELETE",
            url=self._url,
            data=data,
            security=_SEC_USER_STREAM,
        )


def _to_asset(asset: str) -> str:
    return asset.upper()


def _from_asset(asset: str) -> str:
    return asset.lower()


def _to_http_symbol(symbol: str) -> str:
    return symbol.replace("-", "").upper()


def _to_ws_symbol(symbol: str) -> str:
    return symbol.replace("-", "")


# TODO: May be incorrect! We can't systematically know which part is base and which is quote
# since there is no separator used. We simply map based on known quote assets.
_KNOWN_QUOTE_ASSETS = [
    "AUD",
    "BIDR",
    "BNB",
    "BKRW",
    "BRL",
    "BTC",
    "BUSD",
    "BVND",
    "DAI",
    "DOGE",
    "ETH",
    "EUR",
    "GBP",
    "GYEN",
    "IDRT",
    "NGN",
    "PAX",
    "RUB",
    "TRX",
    "TRY",
    "TUSD",
    "UAH",
    "USDC",
    "USDP",
    "USDS",
    "USDT",
    "VAI",
    "XRP",
    "ZAR",
]


def _from_symbol(symbol: str) -> str:
    for asset in _KNOWN_QUOTE_ASSETS:
        if symbol.endswith(asset):
            base = symbol[: -len(asset)]
            quote = asset
            break
    else:
        _log.warning(f"unknown quote asset found in symbol: {symbol}")
        # We round up because usually base asset is the longer one (i.e IOTABTC).
        split_index = math.ceil(len(symbol) / 2)
        base = symbol[:split_index]
        quote = symbol[split_index:]
    return f"{base.lower()}-{quote.lower()}"


def _to_side(side: Side) -> str:
    return {
        Side.BUY: "BUY",
        Side.SELL: "SELL",
    }[side]


def _to_order_type(type_: OrderType) -> str:
    return {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        # OrderType.STOP_LOSS: 'STOP_LOSS',
        # OrderType.STOP_LOSS_LIMIT: 'STOP_LOSS_LIMIT',
        # OrderType.TAKE_PROFIT: 'TAKE_PROFIT',
        # OrderType.TAKE_PROFIT_LIMIT: 'TAKE_PROFIT_LIMIT',
        OrderType.LIMIT_MAKER: "LIMIT_MAKER",
    }[type_]


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    return {
        TimeInForce.GTC: "GTC",
        TimeInForce.IOC: "IOC",
        TimeInForce.FOK: "FOK",
        # TimeInForce.GTT: 'GTT',
    }[time_in_force]


def _from_order_status(status: str) -> OrderStatus:
    status_map = {
        "NEW": OrderStatus.NEW,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "FILLED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELLED,
    }
    mapped_status = status_map.get(status)
    if not mapped_status:
        raise NotImplementedError(f"Handling of status {status} not implemented")
    return mapped_status


def _to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f"{value:f}"
