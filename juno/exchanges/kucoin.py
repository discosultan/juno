from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import Any, AsyncContextManager, AsyncIterable, AsyncIterator, Optional

import juno.json as json
from juno import (
    AssetInfo,
    Balance,
    Depth,
    ExchangeException,
    ExchangeInfo,
    Fees,
    Fill,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    Side,
    TimeInForce,
)
from juno.asyncio import cancel, create_task_sigint_on_exception, stream_queue
from juno.errors import OrderMissing
from juno.filters import Filters, Price, Size
from juno.http import ClientResponse, ClientSession, ClientWebSocketResponse
from juno.math import round_down
from juno.time import DAY_MS, HOUR_MS, MIN_MS, WEEK_MS
from juno.utils import AsyncLimiter, unpack_quote_asset

from .exchange import Exchange

_BASE_URL = "https://api.kucoin.com"

_log = logging.getLogger(__name__)


class KuCoin(Exchange):
    """https://docs.kucoin.com"""

    def __init__(self, api_key: str, secret_key: str, passphrase: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode("utf-8")
        self._passphrase = base64.b64encode(
            hmac.new(self._secret_key_bytes, passphrase.encode("utf-8"), hashlib.sha256).digest()
        ).decode("ascii")
        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)
        self._ws = KuCoinFeed(self)

        # Limiters.
        self._get_depth_limiter = AsyncLimiter(30, 3)
        self._place_order_limiter = AsyncLimiter(45, 3)
        self._cancel_order_limiter = AsyncLimiter(60, 3)

    async def __aenter__(self) -> KuCoin:
        await self._session.__aenter__()
        await self._ws.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._ws.__aexit__(exc_type, exc, tb)
        await self._session.__aexit__(exc_type, exc, tb)

    def map_candle_intervals(self) -> dict[int, int]:
        return {
            MIN_MS: 0,
            3 * MIN_MS: 0,
            5 * MIN_MS: 0,
            15 * MIN_MS: 0,
            30 * MIN_MS: 0,
            HOUR_MS: 0,
            2 * HOUR_MS: 0,
            4 * HOUR_MS: 0,
            6 * HOUR_MS: 0,
            8 * HOUR_MS: 0,
            12 * HOUR_MS: 0,
            DAY_MS: 0,
            WEEK_MS: 0,  # TODO: verify
        }

    async def get_exchange_info(self) -> ExchangeInfo:
        currencies, symbols = await asyncio.gather(
            self._public_request_json("GET", "/api/v1/currencies"),
            self._public_request_json("GET", "/api/v1/symbols"),
        )

        assets = {
            # TODO: Maybe we should use "name" instead of "currency".
            _from_asset(c["currency"]): AssetInfo(precision=c["precision"])
            for c in currencies["data"]
        }
        fees = {
            # TODO: This is for LVL 0 only.
            "__all__": Fees(maker=Decimal("0.001"), taker=Decimal("0.001"))
        }
        filters = {
            _from_symbol(s["symbol"]): Filters(
                price=Price(
                    min=Decimal(s["quoteMinSize"]),
                    max=Decimal(s["quoteMaxSize"]),
                    step=Decimal(s["quoteIncrement"]),
                ),
                size=Size(
                    min=Decimal(s["baseMinSize"]),
                    max=Decimal(s["baseMaxSize"]),
                    step=Decimal(s["baseIncrement"]),
                ),
            )
            for s in symbols["data"]
        }

        return ExchangeInfo(
            assets=assets,
            fees=fees,
            filters=filters,
        )

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        if account != "spot":
            raise NotImplementedError()

        balances = await self._private_request_json("GET", "/api/v1/accounts")
        return {
            "spot": {
                _from_asset(b["currency"]): Balance(
                    available=Decimal(b["available"]),
                    hold=Decimal(b["holds"]),
                )
                for b in balances["data"]
                if b["type"] == "trade"
            }
        }

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        if account != "spot":
            raise NotImplementedError()

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[dict[str, Balance]]:
            async for msg in ws:
                subject = msg["subject"]
                if subject == "trade.balance":
                    data = msg["data"]

                    yield {
                        _from_symbol(data["symbol"]): Balance(
                            available=data["available"],
                            hold=data["hold"],
                        )
                    }
                else:
                    raise NotImplementedError(f"unhandled balance subject {subject}")

        async with self._ws.subscribe("/account/balance") as ws:
            yield inner(ws)

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        await self._get_depth_limiter.acquire()
        depth = (
            await self._private_request_json(
                "GET",
                "/api/v3/market/orderbook/level2",
                params={"symbol": _to_symbol(symbol)},
            )
        )["data"]
        return Depth.Snapshot(
            last_id=int(depth["sequence"]),
            bids=[(Decimal(p), Decimal(s)) for p, s in depth["bids"]],
            asks=[(Decimal(p), Decimal(s)) for p, s in depth["asks"]],
        )

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Any]:
            async for msg in ws:
                subject = msg["subject"]
                if subject == "trade.l2update":
                    data = msg["data"]

                    data_symbol = _from_symbol(data["symbol"])
                    if data_symbol != symbol:
                        raise NotImplementedError(f"received depth for symbol {data_symbol}")

                    changes = data["changes"]
                    yield Depth.Update(
                        bids=[(Decimal(p), Decimal(s)) for p, s, _ in changes["bids"]],
                        asks=[(Decimal(p), Decimal(s)) for p, s, _ in changes["asks"]],
                        first_id=data["sequenceStart"],
                        last_id=data["sequenceEnd"],
                    )
                else:
                    raise NotImplementedError(f"unhandled depth subject {subject}")

        async with self._ws.subscribe(f"/market/level2:{_to_symbol(symbol)}") as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        if account != "spot":
            raise NotImplementedError()

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            async for msg in ws:
                subject = msg["subject"]
                if subject == "orderChange":
                    data = msg["data"]

                    data_symbol = _from_symbol(data["symbol"])
                    if data_symbol != symbol:
                        continue

                    type_ = data["type"]
                    if type_ == "open":
                        yield OrderUpdate.New(
                            client_id=data["clientOid"],
                        )
                    elif type_ == "match":
                        price = Decimal(data["matchPrice"])
                        size = Decimal(data["matchSize"])
                        quote_asset = unpack_quote_asset(data_symbol)
                        yield OrderUpdate.Match(
                            client_id=data["clientOid"],
                            fill=Fill.with_computed_quote(
                                price=price,
                                size=size,
                                # TODO: 8 for most assets, but can also be 6 or 4!
                                precision=8,
                                fee_asset=quote_asset,
                                # TODO: 0.1% maker/taker by default but can be different as well!
                                fee=round_down(price * size * Decimal("0.001"), 8),
                            ),
                        )
                    elif type_ == "filled":
                        yield OrderUpdate.Done(
                            client_id=data["clientOid"],
                            time=data["ts"],
                        )
                    elif type_ == "canceled":
                        yield OrderUpdate.Cancelled(
                            client_id=data["clientOid"],
                            time=data["ts"],
                        )
                    else:
                        raise NotImplementedError(f"unhandled order type {type_}")
                else:
                    raise NotImplementedError(f"unhandled order subject {subject}")

        async with self._ws.subscribe("/spotMarket/tradeOrders") as ws:
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
        if account != "spot":
            raise NotImplementedError()

        await self._place_order_limiter.acquire()

        body: dict[str, Any] = {
            "clientOid": self.generate_client_id() if client_id is None else client_id,
            "side": "buy" if side is Side.BUY else "sell",
            "symbol": _to_symbol(symbol),
            "type": "market" if type_ is OrderType.MARKET else "limit",
        }
        if price is not None:
            body["price"] = str(price)
        if size is not None:
            body["size"] = str(size)
        if quote is not None:
            body["funds"] = str(quote)
        if time_in_force is not None:
            body["timeInForce"] = _to_time_in_force(time_in_force)
            if time_in_force not in {TimeInForce.IOC, TimeInForce.FOK}:
                body["postOnly"] = True

        await self._private_request_json(
            method="POST",
            url="/api/v1/orders",
            body=body,
        )

        # TODO: raise bad order if bad order

        return OrderResult(time=0, status=OrderStatus.NEW)

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        if account != "spot":
            raise NotImplementedError()

        await self._cancel_order_limiter.acquire()

        res = await self._private_request_json(
            method="DELETE",
            url=f"/api/v1/order/client-order/{client_id}",
        )
        if res["code"] == "400100":
            raise OrderMissing()

    async def _public_request_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
    ) -> Any:
        response = await self._request(method=method, url=url, params=params)
        response.raise_for_status()
        return await response.json()

    async def _private_request_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Any:
        timestamp = str(int(time.time() * 1000))
        str_to_sign = timestamp + method + url
        if params is not None:
            str_to_sign += "?"
            str_to_sign += "&".join(f"{k}={v}" for k, v in params.items())
        if body is not None:
            str_to_sign += json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        signature = base64.b64encode(
            hmac.new(self._secret_key_bytes, str_to_sign.encode("utf-8"), hashlib.sha256).digest()
        ).decode("ascii")
        headers: dict[str, str] = {
            "KC-API-KEY": self._api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": self._passphrase,
            "KC-API-KEY-VERSION": "2",
        }
        response = await self._request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
        )
        response.raise_for_status()
        return await response.json()

    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, str]] = None,
        body: Any = None,
    ) -> ClientResponse:
        async with self._session.request(
            method=method,
            url=_BASE_URL + url,
            headers=headers,
            params=params,
            json=body,
        ) as response:
            if response.status >= 500:
                raise ExchangeException(await response.text())
            return response


class KuCoinFeed:
    def __init__(self, client: KuCoin) -> None:
        self._client = client
        self._session = ClientSession(raise_for_status=True, name=type(self).__name__)

        self._ws_lock = asyncio.Lock()
        self._ws_ctx: Optional[AsyncContextManager[ClientWebSocketResponse]] = None
        self._ws: Optional[ClientWebSocketResponse] = None

        self._process_task: Optional[asyncio.Task] = None

        self._queues: dict[str, dict[str, asyncio.Queue]] = defaultdict(
            lambda: defaultdict(asyncio.Queue)
        )

    async def __aenter__(self) -> KuCoinFeed:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await cancel(self._process_task)
        if self._ws:
            await self._ws.close()
        if self._ws_ctx:
            await self._ws_ctx.__aexit__(exc_type, exc, tb)
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def subscribe(self, topic: str) -> AsyncIterator[AsyncIterable[Any]]:
        queue_id = str(uuid.uuid4())
        _log.info(f"subscribing to {topic} with queue id {queue_id}")
        ws = await self._ensure_connection()
        await ws.send_json(
            {
                "type": "subscribe",
                "topic": topic,
            }
        )
        _log.info(f"subscribed to {topic} with queue id {queue_id}")

        event_queues = self._queues[topic]
        try:
            yield stream_queue(event_queues[queue_id], raise_on_exc=True)
        finally:
            del event_queues[queue_id]
            # TODO: unsubscribe
            # TODO: Cancel WS if no subscriptions left.

    async def _ensure_connection(self) -> ClientWebSocketResponse:
        if self._ws:
            return self._ws
        async with self._ws_lock:
            if self._ws:
                return self._ws

            res = (await self._client._private_request_json("POST", "/api/v1/bullet-private"))[
                "data"
            ]
            instance = res["instanceServers"][0]
            self._ws_ctx = self._session.ws_connect(
                url=instance["endpoint"] + "?token=" + res["token"],
                heartbeat=instance["pingInterval"] / 1000,
                # TODO: Can we also use pingTimeout?
            )
            self._ws = await self._ws_ctx.__aenter__()
            self._process_task = create_task_sigint_on_exception(self._stream_messages(self._ws))
            return self._ws

    async def _stream_messages(self, ws: ClientWebSocketResponse) -> None:
        async for msg in ws:
            data = json.loads(msg.data)
            if data["type"] == "welcome":
                _log.info("received ws welcome")
                continue
            event_queues = self._queues[data["topic"]]
            for queue in event_queues.values():
                queue.put_nowait(data)


def _from_asset(asset: str) -> str:
    return asset.lower()


def _from_symbol(symbol: str) -> str:
    return symbol.lower()


def _to_symbol(symbol: str) -> str:
    return symbol.upper()


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    if time_in_force is TimeInForce.FOK:
        return "FOK"
    if time_in_force is TimeInForce.GTC:
        return "GTC"
    if time_in_force is TimeInForce.IOC:
        return "IOC"
    # They also support GTT but we don't.
    raise NotImplementedError()
