from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncContextManager, AsyncIterable, AsyncIterator, Optional

from juno import (
    AssetInfo,
    Balance,
    Candle,
    Depth,
    ExchangeInfo,
    Fees,
    Fill,
    Filters,
    Interval_,
    Order,
    OrderMissing,
    OrderResult,
    OrderType,
    OrderUpdate,
    Side,
    Symbol_,
    Ticker,
    TimeInForce,
    Timestamp_,
    Trade,
    json,
)
from juno.aiolimiter import AsyncLimiter
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, stream_queue
from juno.common import OrderStatus
from juno.filters import Price, Size
from juno.http import ClientSession, ClientWebSocketResponse
from juno.math import precision_to_decimal
from juno.typing import ExcType, ExcValue, Traceback

from .exchange import Exchange

# https://www.kraken.com/features/api
_API_URL = "https://api.kraken.com"

# https://docs.kraken.com/websockets/
# https://support.kraken.com/hc/en-us/articles/360022326871-Public-WebSockets-API-common-questions
_PUBLIC_WS_URL = "wss://ws.kraken.com"
_PRIVATE_WS_URL = "wss://ws-auth.kraken.com"

_log = logging.getLogger(__name__)


class Kraken(Exchange):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = True
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False
    can_list_all_tickers: bool = False
    can_margin_trade: bool = False  # TODO: Actually can; need impl
    can_place_market_order: bool = True
    can_place_market_order_quote: bool = False  # TODO: Can but only for non-leveraged orders

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._decoded_secret_key = base64.b64decode(secret_key)

    async def __aenter__(self) -> Kraken:
        # Rate limiters.
        # TODO: This is Starter rate. The rate differs for Intermediate and Pro users.
        self._reqs_limiter = AsyncLimiter(15, 45)
        self._order_placing_limiter = AsyncLimiter(1, 1.5)  # Originally 1, 1

        self._session = ClientSession(raise_for_status=True, name=type(self).__name__)
        await self._session.__aenter__()

        self._public_ws = KrakenPublicFeed(_PUBLIC_WS_URL)
        self._private_ws = KrakenPrivateFeed(_PRIVATE_WS_URL, self)
        await asyncio.gather(
            self._public_ws.__aenter__(),
            self._private_ws.__aenter__(),
        )

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            self._private_ws.__aexit__(exc_type, exc, tb),
            self._public_ws.__aexit__(exc_type, exc, tb),
        )
        await self._session.__aexit__(exc_type, exc, tb)

    def generate_client_id(self) -> int | str:
        # Have to convert to seconds because only 32 bits are allowed.
        return Timestamp_.now() // 1000

    def list_candle_intervals(self) -> list[int]:
        return [
            60000,  # 1m
            300000,  # 5m
            900000,  # 15m
            1800000,  # 30m
            3600000,  # 1h
            14400000,  # 4h
            86400000,  # 1d
            604800000,  # 1w
            1296000000,  # 15d
        ]

    async def get_exchange_info(self) -> ExchangeInfo:
        assets_res, symbols_res = await asyncio.gather(
            self._request_public("GET", "/0/public/Assets"),
            self._request_public("GET", "/0/public/AssetPairs"),
        )

        assets = {
            _from_asset(key): AssetInfo(precision=val["decimals"])
            for key, val in assets_res["result"].items()
        }

        fees, filters = {}, {}
        for key, val in symbols_res["result"].items():
            name = _from_symbol(key)
            # TODO: Take into account different fee levels. Currently only worst level.
            taker_fee = val["fees"][0][1] / 100
            maker_fees = val.get("fees_maker")
            fees[name] = Fees(
                maker=maker_fees[0][1] / 100 if maker_fees else taker_fee, taker=taker_fee
            )
            filters[name] = Filters(
                base_precision=(base_precision := val["lot_decimals"]),
                quote_precision=(quote_precision := val["pair_decimals"]),
                size=Size(
                    step=precision_to_decimal(base_precision),  # type: ignore
                ),
                price=Price(
                    step=precision_to_decimal(quote_precision),  # type: ignore
                ),
            )

        return ExchangeInfo(
            assets=assets,
            fees=fees,
            filters=filters,
        )

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        """https://docs.kraken.com/rest/#operation/getTickerInformation"""

        if not symbols:
            raise ValueError("Empty symbols list not supported")

        data = {"pair": ",".join((_to_http_symbol(s) for s in symbols))}

        res = await self._request_public("GET", "/0/public/Ticker", data=data)
        return {
            _from_symbol(pair): Ticker(
                volume=Decimal(val["v"][1]),
                quote_volume=Decimal("0.0"),  # Not supported.
                price=Decimal(val["c"][0]),
            )
            for pair, val in res["result"].items()
        }

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        """https://docs.kraken.com/rest/#operation/getAccountBalance"""

        result = {}
        if account == "spot":
            res = await self._request_private("/0/private/Balance")
            result["spot"] = {
                _from_asset(a): Balance(
                    available=Decimal(v),
                    hold=Decimal("0.0"),  # Not supported.
                )
                for a, v in res["result"].items()
            }
        else:
            raise NotImplementedError()
        return result

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        # https://docs.kraken.com/websockets/#message-ohlc
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for c in ws:
                # TODO: Kraken doesn't publish candles for intervals where there are no trades.
                # We should fill those caps ourselves.
                # They also send multiple candles per interval. We need to determine when a candle
                # is closed ourselves. Trickier than with Binance.
                yield Candle(
                    # They provide end and not start time, hence we subtract interval.
                    time=int(Decimal(c[1]) * 1000) - interval,
                    open=Decimal(c[2]),
                    high=Decimal(c[3]),
                    low=Decimal(c[4]),
                    close=Decimal(c[5]),
                    volume=Decimal(c[7]),
                )

        async with self._public_ws.subscribe(
            {"name": "ohlc", "interval": interval // Interval_.MIN}, [_to_ws_symbol(symbol)]
        ) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Any]:
            async for val in ws:
                if "as" in val or "bs" in val:
                    bids = val.get("bs", [])
                    asks = val.get("as", [])
                    yield Depth.Snapshot(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )
                else:
                    bids = val.get("b", [])
                    asks = val.get("a", [])
                    yield Depth.Update(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )

        async with self._public_ws.subscribe(
            {
                "name": "book",
                "depth": 10,
            },
            [_to_ws_symbol(symbol)],
        ) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(
        self,
        account: str,
        symbol: str,
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        """https://docs.kraken.com/websockets/#message-openOrders"""

        assert account == "spot"

        quote_asset = Symbol_.quote_asset(symbol)

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            is_first = True
            async for o in ws:
                # The first message lists all existing open orders. Discard it.
                # TODO: Fails if we have multiple consumers
                if is_first:
                    is_first = False
                    continue
                updates = o[0]
                for update in updates.values():
                    client_id = update["userref"]
                    status = update.get("status")
                    if status == "open":
                        yield OrderUpdate.New(
                            client_id=client_id,
                        )
                    elif status == "canceled":
                        yield OrderUpdate.Cancelled(
                            time=_from_ws_time(update["lastupdated"]),
                            client_id=client_id,
                        )
                    elif status == "closed":
                        yield OrderUpdate.Done(
                            time=_from_ws_time(update["lastupdated"]),
                            client_id=client_id,
                        )
                    elif status == "pending":
                        pass
                    elif status is None:  # Match.
                        yield OrderUpdate.Match(
                            client_id=client_id,
                            fill=Fill(
                                price=Decimal(update["avg_price"]),
                                size=Decimal(update["vol_exec"]),
                                quote=Decimal(update["cost"]),
                                fee=Decimal(update["fee"]),
                                fee_asset=quote_asset,
                            ),
                        )
                    else:
                        raise NotImplementedError(f"Unhandled status: {status}")

        async with self._private_ws.subscribe({"name": "openOrders"}) as ws:
            yield inner(ws)

    async def list_orders(self, account: str, symbol: Optional[str] = None) -> list[Order]:
        """https://docs.kraken.com/rest/#operation/getOpenOrders"""

        assert account == "spot"

        res = await self._request_private("/0/private/OpenOrders")
        return [
            Order(
                client_id=o["userref"],
                symbol=order_symbol,
                price=Decimal(o["price"]),
                size=Decimal(o["vol"]),
            )
            for o in res["result"]["open"].values()
            if symbol is None or (order_symbol := _from_symbol(o["descr"]["pair"])) == symbol
        ]

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
        client_id: Optional[str | int] = None,
    ) -> OrderResult:
        """https://docs.kraken.com/rest/#operation/addOrder"""
        # TODO: use order placing limiter instead of default.

        assert account == "spot"
        assert quote is None

        flags = []
        if type_ is OrderType.LIMIT_MAKER:
            flags.append("post")

        data: dict[str, Any] = {
            "ordertype": _to_order_type(type_),
            "type": _to_side(side),
            "pair": _to_http_symbol(symbol),
        }
        if client_id is not None:
            data["userref"] = client_id
        if price is not None:
            data["price"] = str(price)
        if size is not None:
            data["volume"] = str(size)
        if time_in_force is not None:
            data["timeinforce"] = _to_time_in_force(time_in_force)
        if len(flags) > 0:
            data["oflags"] = ",".join(flags)

        await self._request_private(
            url="/0/private/AddOrder",
            data=data,
            limiter=self._order_placing_limiter,
        )
        # TODO: Just a dummy result.
        return OrderResult(time=Timestamp_.now(), status=OrderStatus.NEW)

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str | int,
    ) -> None:
        """https://docs.kraken.com/rest/#operation/cancelOrder"""
        # TODO: use order placing limiter instead of default.

        assert account == "spot"

        try:
            await self._request_private(
                url="/0/private/CancelOrder",
                data={
                    "txid": client_id,
                },
                limiter=self._order_placing_limiter,
            )
        except KrakenException as exc:
            if len(exc.errors) == 1 and (msg := exc.errors[0]).startswith("EOrder:"):
                raise OrderMissing(msg)
            raise

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        # https://www.kraken.com/en-us/features/api#get-recent-trades
        since = _to_time(start) - 1  # Exclusive.
        while True:
            res = await self._request_public(
                "GET",
                "/0/public/Trades",
                {"pair": _to_http_symbol(symbol), "since": since},
                cost=2,
            )
            result = res["result"]
            last = result["last"]

            if last == since:  # No more trades returned.
                break

            since = last
            _, trades = next(iter(result.items()))
            for trade in trades:
                time = _from_time(trade[2])
                if time >= end:
                    return
                yield Trade(
                    time=time,
                    price=Decimal(trade[0]),
                    size=Decimal(trade[1]),
                )

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for trades in ws:
                for trade in trades:
                    yield Trade(
                        time=_from_ws_time(trade[2]),
                        price=Decimal(trade[0]),
                        size=Decimal(trade[1]),
                    )

        async with self._public_ws.subscribe({"name": "trade"}, [_to_ws_symbol(symbol)]) as ws:
            yield inner(ws)

    async def _get_websockets_token(self) -> str:
        res = await self._request_private("/0/private/GetWebSocketsToken")
        return res["result"]["token"]

    async def _request_public(
        self, method: str, url: str, data: Optional[Any] = None, cost: int = 1
    ) -> Any:
        data = data or {}
        return await self._request(method, url, data, {}, self._reqs_limiter, cost)

    async def _request_private(
        self,
        url: str,
        data: Optional[dict[str, Any]] = None,
        cost: int = 1,
        limiter: Optional[AsyncLimiter] = None,
    ) -> Any:
        if limiter is None:
            limiter = self._reqs_limiter

        data = data or {}
        nonce = Timestamp_.now()
        data["nonce"] = nonce
        # TODO: support OTP
        # if enabled:
        #   data['otp] = 'password'

        querystr = urllib.parse.urlencode(data)
        encoded = (str(nonce) + querystr).encode()
        message = url.encode() + hashlib.sha256(encoded).digest()
        signature = hmac.new(self._decoded_secret_key, message, hashlib.sha512)

        headers = {
            "API-Key": self._api_key,
            "API-Sign": base64.b64encode(signature.digest()).decode(),
        }
        return await self._request("POST", url, data, headers, limiter, cost)

    async def _request(
        self,
        method: str,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str],
        limiter: AsyncLimiter,
        cost: int,
    ) -> Any:
        if limiter is None:
            limiter = self._reqs_limiter
        if cost > 0:
            await limiter.acquire(cost)

        async with self._session.request(
            method=method,
            url=_API_URL + url,
            headers=headers,
            params=data if method == "GET" else None,
            data=None if method == "GET" else data,
        ) as res:
            result = await res.json()
            errors = result["error"]
            if len(errors) > 0:
                raise KrakenException(f"Received error(s) from Kraken: {errors}", errors)
            return result


class KrakenPublicFeed:
    def __init__(self, url: str) -> None:
        self.url = url

        self.session = ClientSession(raise_for_status=True, name=type(self).__name__)
        self.ws_ctx: Optional[AsyncContextManager[ClientWebSocketResponse]] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        self.ws_lock = asyncio.Lock()
        self.process_task: Optional[asyncio.Task] = None

        self.reqid = 1
        self.subscriptions: dict[int, Event[asyncio.Queue[Any]]] = defaultdict(
            lambda: Event(autoclear=True)
        )
        self.channels: dict[int, asyncio.Queue[Any]] = defaultdict(asyncio.Queue)

    async def __aenter__(self) -> KrakenPublicFeed:
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self.process_task)
        if self.ws:
            await self.ws.close()
        if self.ws_ctx:
            await self.ws_ctx.__aexit__(exc_type, exc, tb)
        await self.session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def subscribe(
        self, subscription: Any, symbols: Optional[list[str]] = None
    ) -> AsyncIterator[AsyncIterable[Any]]:
        await self._ensure_connection()

        reqid = self.reqid
        subscribed = self.subscriptions[reqid]
        self.reqid += 1
        payload = {
            "event": "subscribe",
            "reqid": reqid,
            "subscription": subscription,
        }
        if symbols is not None:
            payload["pair"] = symbols

        await self._send(payload)

        received = await subscribed.wait()

        try:
            yield stream_queue(received)
        finally:
            # TODO: unsubscribe
            pass

    async def _send(self, msg: Any) -> None:
        assert self.ws
        await self.ws.send_json(msg)

    async def _ensure_connection(self) -> None:
        async with self.ws_lock:
            if self.ws:
                return
            await self._connect()

    async def _connect(self) -> None:
        self.ws_ctx = self.session.ws_connect(self.url)
        self.ws = await self.ws_ctx.__aenter__()
        self.process_task = create_task_sigint_on_exception(self._stream_messages())

    async def _stream_messages(self) -> None:
        assert self.ws
        async for msg in self.ws:
            data = json.loads(msg.data)
            self._process_message(data)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data["event"] == "subscriptionStatus":
                _validate_subscription_status(data)
                subscribed = self.subscriptions[data["reqid"]]
                received = self.channels[data["channelID"]]
                subscribed.set(received)
        else:  # List.
            channel_id = data[0]

            if len(data) > 4:
                # Consolidate.
                val: Any = {}
                for consolidate in data[1 : len(data) - 2]:
                    val.update(consolidate)
            else:
                val = data[1]

            # type_ = data[-2]
            # pa_onir = data[-1]
            self.channels[channel_id].put_nowait(val)  # type: ignore


class KrakenPrivateFeed(KrakenPublicFeed):
    def __init__(self, url: str, kraken: Kraken) -> None:
        super().__init__(url)
        self.kraken = kraken

    async def _connect(self) -> None:
        _, token = await asyncio.gather(super()._connect(), self.kraken._get_websockets_token())
        self.token = token

    async def _send(self, payload: Any) -> None:
        payload["subscription"]["token"] = self.token
        await super()._send(payload)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data["event"] == "subscriptionStatus":
                _validate_subscription_status(data)
                subscribed = self.subscriptions[data["reqid"]]
                received = self.channels[data["channelName"]]
                subscribed.set(received)
        else:  # List.
            channel_id = data[1]
            self.channels[channel_id].put_nowait(data[0])  # type: ignore


class KrakenException(Exception):
    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


def _validate_subscription_status(data: Any) -> None:
    if data["status"] == "error":
        raise Exception(data["errorMessage"])


def _from_time(time: Decimal) -> int:
    # Convert seconds to milliseconds.
    return int(time * 1000)


def _from_ws_time(time: str) -> int:
    # Convert seconds to milliseconds.
    return int(Decimal(time) * 1000)


def _to_time(time: int) -> int:
    # Convert milliseconds to nanoseconds.
    return time * 1_000_000


def _to_ws_symbol(symbol: str) -> str:
    return symbol.replace("-", "/").upper()


# The asset names we are dealing with can be in three different forms:
#
# 1. Kraken old format = xxbt
# 2. Kraken new format = xbt
# 3. Juno format       = btc
#
# Similarly with symbols:
#
# 1. Kraken old format = xethxxbt
# 2. Kraken new format = ethxbt
# 3. Juno format       = eth-btc
#
# We always go first from 1. -> 2. and then from 2. -> 3..

_OLD_SYMBOL_TO_NEW_SYMBOL = {
    "xetcxxbt": "etcxbt",
    "xethxxbt": "ethxbt",
    "xltcxxbt": "ltcxbt",
    "xmlnxxbt": "mlnxbt",
    "xrepxxbt": "repxbt",
    "xxbtzcad": "xbtcad",
    "xxbtzeur": "xbteur",
    "xxbtzgbp": "xbtgbp",
    "xxbtzjpy": "xbtjpy",
    "xxbtzusd": "xbtusd",
    "xxdgxxbt": "xdgxbt",
    "xxlmxxbt": "xlmxbt",
    "xxmrxxbt": "xmrxbt",
    "xxrpxxbt": "xrpxbt",
    "xzecxxbt": "zecxbt",
    "xetcxeth": "etceth",
    "xethzcad": "ethcad",
    "xethzeur": "etheur",
    "xethzgbp": "ethgbp",
    "xethzjpy": "ethjpy",
    "xethzusd": "ethusd",
    "xmlnxeth": "mlneth",
    "xrepxeth": "repeth",
    "xetczeur": "etceur",
    "xetczusd": "etcusd",
    "xltczeur": "ltceur",
    "xltczjpy": "ltcjpy",
    "xltczusd": "ltcusd",
    "xmlnzeur": "mlneur",
    "xmlnzusd": "mlnusd",
    "xrepzeur": "repeur",
    "xrepzusd": "repusd",
    "xxlmzaud": "xlmaud",
    "xxlmzeur": "xlmeur",
    "xxlmzgbp": "xlmgbp",
    "xxlmzusd": "xlmusd",
    "xxmrzeur": "xmreur",
    "xxmrzusd": "xmrusd",
    "xzeczeur": "zeceur",
    "xzeczusd": "zecusd",
}

_OLD_ASSET_TO_NEW_ASSET = {
    "xxbt": "xbt",
    "xxdg": "xdg",
    "xetc": "etc",
    "xeth": "eth",
    "xltc": "ltc",
    "xmln": "mln",
    "xxlm": "xlm",
    "xxmr": "xmr",
    "xxrp": "xrp",
    "xzec": "zec",
    "zaud": "aud",
    "zcad": "cad",
    "zeur": "eur",
    "zgbp": "gbp",
    "zjpy": "jpy",
    "zusd": "usd",
}

_KNOWN_NEW_QUOTE_ASSETS = [
    "eur",
    "usd",
    "aud",
    "eth",
    "gbp",
    "xbt",
    "jpy",
    "usdt",
    "chf",
    "dai",
    "usdc",
    "cad",
    "dot",
]

_ASSET_ALIAS_MAP = {
    "xbt": "btc",
    "xdg": "doge",
}
_REVERSE_ASSET_ALIAS_MAP = {v: k for k, v in _ASSET_ALIAS_MAP.items()}


def _from_asset(asset: str) -> str:
    # 1. Normalize to lowercase.
    asset = asset.lower()
    # 2. Go from Kraken old format to new format.
    asset = _OLD_ASSET_TO_NEW_ASSET.get(asset, asset)
    # 3. Go from Kraken new format to Juno format.
    return _ASSET_ALIAS_MAP.get(asset, asset)


def _from_symbol(symbol: str) -> str:
    # 1. Normalize to lowercase.
    symbol = symbol.lower()
    # 2. Go from Kraken old format to new format.
    symbol = _OLD_SYMBOL_TO_NEW_SYMBOL.get(symbol, symbol)
    # 3. Go from Kraken new format to Juno format.
    for asset in _KNOWN_NEW_QUOTE_ASSETS:
        if symbol.endswith(asset):
            base = symbol[: -len(asset)]
            base = _ASSET_ALIAS_MAP.get(base, base)
            quote = _ASSET_ALIAS_MAP.get(asset, asset)
            break
    else:
        raise NotImplementedError(f"unknown quote asset found in symbol: {symbol}")

    return f"{base}-{quote}"


def _to_http_symbol(symbol: str) -> str:
    # 1. Go from Juno format to Kraken new format.
    base, quote = Symbol_.assets(symbol)
    base = _REVERSE_ASSET_ALIAS_MAP.get(base, base)
    quote = _REVERSE_ASSET_ALIAS_MAP.get(quote, quote)
    # 2. Transform to uppercase.
    return (f"{base}{quote}").upper()


def _to_order_type(order_type: OrderType) -> str:
    if order_type in {OrderType.LIMIT, OrderType.LIMIT_MAKER}:
        return "limit"
    if order_type is OrderType.MARKET:
        return "market"
    raise NotImplementedError()


def _to_side(side: Side) -> str:
    if side is Side.BUY:
        return "buy"
    if side is Side.SELL:
        return "sell"
    raise NotImplementedError()


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    if time_in_force is TimeInForce.GTC:
        return "GTC"
    if time_in_force is TimeInForce.IOC:
        return "IOC"
    raise NotImplementedError()
