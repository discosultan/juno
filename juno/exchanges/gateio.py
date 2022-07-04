from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from decimal import Decimal
from time import time
from types import TracebackType
from typing import Any, AsyncIterable, AsyncIterator, Optional
from urllib.parse import urlencode

from juno import json
from juno.common import (
    Balance,
    Candle,
    Depth,
    ExchangeInfo,
    Fees,
    Fill,
    Filters,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    Side,
    TimeInForce,
)
from juno.errors import OrderMissing, OrderWouldBeTaker
from juno.filters import MinNotional, Price, Size
from juno.http import ClientResponse, ClientSession
from juno.math import precision_to_decimal
from juno.utils import short_uuid4

from .exchange import Exchange

# https://www.gate.io/docs/apiv4/en/index.html#gate-api-v4
_API_URL = "https://api.gateio.ws"
_WS_URL = "wss://api.gateio.ws/ws/v4/"


class GateIO(Exchange):
    def __init__(self, api_key: str, secret_key: str, high_precision: bool = True) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode("utf-8")
        self._high_precision = high_precision
        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)

    def generate_client_id(self) -> str:
        return short_uuid4()

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
        content = await self._request_json("GET", "/api/v4/spot/currency_pairs")

        fees, filters = {}, {}
        for pair in (c for c in content if c["trade_status"] == "tradable"):
            symbol = _from_symbol(pair["id"])
            # TODO: Take into account different fee levels. Currently only worst level.
            fee = Decimal(pair["fee"]) / 100
            fees[symbol] = Fees(maker=fee, taker=fee)
            filters[symbol] = Filters(
                base_precision=(base_precision := pair["amount_precision"]),
                quote_precision=(quote_precision := pair["precision"]),
                size=Size(
                    min=(
                        Decimal("0.0")
                        if (min_base_amount := pair.get("min_base_amount")) is None
                        else Decimal(min_base_amount)
                    ),
                    step=precision_to_decimal(base_precision),  # type: ignore
                ),
                price=Price(
                    step=precision_to_decimal(quote_precision),  # type: ignore
                ),
                min_notional=MinNotional(
                    min_notional=(
                        Decimal("0.0")
                        if (min_quote_amount := pair.get("min_quote_amount")) is None
                        else Decimal(min_quote_amount)
                    ),
                ),
            )

        return ExchangeInfo(
            fees=fees,
            filters=filters,
        )

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # https://www.gate.io/docs/apiv4/en/index.html#retrieve-order-book
        content = await self._request_json(
            "GET",
            "/api/v4/spot/order_book",
            params={
                "currency_pair": _to_symbol(symbol),
                "with_id": "true",
            },
        )
        return Depth.Snapshot(
            asks=[(Decimal(price), Decimal(size)) for price, size in content["asks"]],
            bids=[(Decimal(price), Decimal(size)) for price, size in content["bids"]],
            last_id=content["id"],
        )

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        channel = "spot.order_book_update"

        # https://www.gateio.pro/docs/apiv4/ws/index.html#changed-order-book-levels
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data["channel"] != channel or data["event"] != "update":
                    continue

                data = data["result"]
                yield Depth.Update(
                    bids=[(Decimal(price), Decimal(size)) for price, size in data["b"]],
                    asks=[(Decimal(price), Decimal(size)) for price, size in data["a"]],
                    first_id=data["U"],
                    last_id=data["u"],
                )

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            await ws.send_json(
                {
                    "time": int(time()),
                    "channel": channel,
                    "event": "subscribe",  # 'unsubscribe' for unsubscription
                    "payload": [_to_symbol(symbol), "100ms" if self._high_precision else "1000ms"],
                }
            )
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
        assert account == "spot"
        assert type_ in [OrderType.LIMIT, OrderType.LIMIT_MAKER]
        assert quote is None
        assert size is not None
        assert price is not None

        ot, tif = _to_order_type_and_time_in_force(type_, time_in_force)

        body: dict[str, Any] = {
            "currency_pair": _to_symbol(symbol),
            "type": ot,
            "side": _to_side(side),
            "price": _to_decimal(price),
            "amount": _to_decimal(size),
        }
        if client_id is not None:
            body["text"] = f"t-{client_id}"
        if tif is not None:
            body["time_in_force"] = tif
        async with self._request_signed("POST", "/api/v4/spot/orders", body=body) as response:
            if response.status == 400:
                error = await response.json()
                if error["label"] == "POC_FILL_IMMEDIATELY":
                    raise OrderWouldBeTaker(error["message"])
            response.raise_for_status()
            content = await response.json()

        assert content["status"] != "cancelled"

        return OrderResult(
            time=_from_timestamp(content["create_time"]),
            status=OrderStatus.NEW,
        )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        # NB! Custom client id will not be available anymore if the order has been up for more than
        # 30 min.
        assert account == "spot"

        params = {
            "currency_pair": _to_symbol(symbol),
        }

        async with self._request_signed(
            "DELETE",
            f"/api/v4/spot/orders/t-{client_id}",
            params=params,
        ) as response:
            if response.status == 404:
                content = await response.json()
                raise OrderMissing(content["message"])

            response.raise_for_status()

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == "spot"
        channel = "spot.orders"
        # We need to track orders here because GateIO doesn't provide trade-level info, but only
        # accumulated updates.
        track_orders = {}

        # https://www.gateio.pro/docs/apiv4/ws/index.html#client-subscription-7
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data["channel"] != channel or data["event"] != "update":
                    continue

                for order in data["result"]:
                    client_id = order["text"][2:]
                    event = order["event"]
                    if event == "put":
                        track_orders[client_id] = {
                            "acc_size": Decimal("0.0"),  # Base.
                            "acc_quote": Decimal("0.0"),  # Quote.
                            "acc_fee": Decimal("0.0"),
                        }
                        yield OrderUpdate.New(client_id=client_id)
                    elif event == "update":
                        yield OrderUpdate.Match(
                            client_id=client_id,
                            fill=_acc_order_fill(track_orders[client_id], order),
                        )
                    elif event == "finish":
                        time = _from_timestamp(order["update_time"])
                        if order["left"] == "0":
                            yield OrderUpdate.Match(
                                client_id=client_id,
                                fill=_acc_order_fill(track_orders[client_id], order),
                            )
                            yield OrderUpdate.Done(
                                client_id=client_id,
                                time=time,
                            )
                        else:
                            yield OrderUpdate.Cancelled(
                                client_id=client_id,
                                time=time,
                            )
                        del track_orders[client_id]
                    else:
                        raise NotImplementedError()

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            time_sec = int(time())
            event = "subscribe"  # 'unsubscribe' for unsubscription
            await ws.send_json(
                {
                    "time": time_sec,
                    "channel": channel,
                    "event": event,
                    "payload": [_to_symbol(symbol)],  # Can pass '!all' for all symbols.
                    "auth": self._gen_ws_sign(channel, event, time_sec),
                }
            )
            yield inner(ws)

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        assert account == "spot"
        result = {}
        content = await self._request_signed_json("GET", "/api/v4/spot/accounts")
        result["spot"] = {
            _from_asset(balance["currency"]): Balance(
                available=Decimal(balance["available"]),
                hold=Decimal(balance["locked"]),
            )
            for balance in content
        }
        return result

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        assert account == "spot"
        channel = "spot.balances"

        # https://www.gateio.pro/docs/apiv4/ws/index.html#client-subscription-9
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[dict[str, Balance]]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data["channel"] != channel or data["event"] != "update":
                    continue

                yield {
                    _from_asset(b["currency"]): Balance(
                        available=(available := Decimal(b["available"])),
                        hold=Decimal(b["total"]) - available,
                    )
                    for b in data["result"]
                }

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            time_sec = int(time())
            event = "subscribe"  # 'unsubscribe' for unsubscription
            await ws.send_json(
                {
                    "time": time_sec,
                    "channel": channel,
                    "event": event,
                    "auth": self._gen_ws_sign(channel, event, time_sec),
                }
            )
            yield inner(ws)

    @asynccontextmanager
    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> AsyncIterator[ClientResponse]:
        if headers is None:
            headers = {}
        headers.update({"Accept": "application/json", "Content-Type": "application/json"})

        async with self._session.request(
            method=method,
            url=_API_URL + url,
            headers=headers,
            **kwargs,
        ) as response:
            yield response

    @asynccontextmanager
    async def _request_signed(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, str]] = None,
    ) -> AsyncIterator[ClientResponse]:
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":"))

        query_string = None
        if params is not None:
            query_string = urlencode(params)

        headers = self._gen_sign(method, url, query_string=query_string, data=data)

        if query_string is not None:
            url += f"?{query_string}"

        async with self._request(method, url, headers, data=data) as response:
            yield response

    async def _request_json(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        async with self._request(
            method=method,
            url=url,
            headers=headers,
            **kwargs,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def _request_signed_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, str]] = None,
    ) -> Any:
        async with self._request_signed(method, url, params=params, body=body) as response:
            response.raise_for_status()
            return await response.json()

    def _gen_sign(
        self,
        method: str,
        url: str,
        query_string: Optional[str] = None,
        data: Optional[str] = None,
    ) -> dict[str, str]:
        # https://www.gate.io/docs/apiv4/en/index.html#api-signature-string-generation
        t = time()
        m = hashlib.sha512()
        m.update((data or "").encode("utf-8"))
        hashed_payload = m.hexdigest()
        s = f'{method}\n{url}\n{query_string or ""}\n{hashed_payload}\n{t}'
        sign = hmac.new(self._secret_key_bytes, s.encode("utf-8"), hashlib.sha512).hexdigest()
        return {"KEY": self._api_key, "Timestamp": str(t), "SIGN": sign}

    def _gen_ws_sign(self, channel: str, event: str, timestamp: int):
        s = f"channel={channel}&event={event}&time={timestamp}"
        sign = hmac.new(self._secret_key_bytes, s.encode("utf-8"), hashlib.sha512).hexdigest()
        return {"method": "api_key", "KEY": self._api_key, "SIGN": sign}

    def list_candle_intervals(self) -> list[int]:
        raise NotImplementedError()

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        raise NotImplementedError()
        yield


def _acc_order_fill(existing: dict[str, Decimal], data: Any) -> Fill:
    acc_size = Decimal(data["amount"]) - Decimal(data["left"])
    acc_quote = Decimal(data["filled_total"])
    acc_fee = Decimal(data["fee"])
    size = acc_size - existing["acc_size"]
    quote = acc_quote - existing["acc_quote"]
    fee = acc_fee - existing["acc_fee"]
    existing["acc_size"] = acc_size
    existing["acc_quote"] = acc_quote
    existing["acc_fee"] = acc_fee
    return Fill(
        price=Decimal(data["price"]),
        size=size,
        quote=quote,
        fee=fee,
        fee_asset=_from_asset(data["fee_currency"]),
    )


def _from_asset(asset: str) -> str:
    return asset.lower()


def _from_symbol(symbol: str) -> str:
    return symbol.lower().replace("_", "-")


def _to_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "_")


def _from_timestamp(timestamp: str) -> int:
    return int(timestamp) * 1000


def _to_order_type_and_time_in_force(
    type: OrderType, time_in_force: Optional[TimeInForce]
) -> tuple[str, Optional[str]]:
    ot = "limit"
    tif = None

    if type not in [OrderType.LIMIT, OrderType.LIMIT_MAKER]:
        raise NotImplementedError()

    if type is OrderType.LIMIT_MAKER:
        assert time_in_force is None
        tif = "poc"
    elif time_in_force is TimeInForce.IOC:
        tif = "ioc"
    elif time_in_force is TimeInForce.GTC:
        tif = "gtc"
    elif time_in_force is TimeInForce.FOK:
        raise NotImplementedError()

    return ot, tif


def _to_side(side: Side) -> str:
    if side is Side.BUY:
        return "buy"
    if side is Side.SELL:
        return "sell"
    raise NotImplementedError()


def _to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f"{value:f}"
