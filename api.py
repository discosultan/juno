import logging
import os
from decimal import Decimal
from functools import partial
from typing import AsyncIterator, Optional, Type, TypedDict, TypeVar

import aiohttp_cors
from aiohttp import web

from juno import (
    Asset,
    Candle,
    CandleType,
    ExchangeInfo,
    Interval,
    Timestamp,
    json,
    serialization,
    yaml,
)
from juno.components import Chandler, Informant, Prices, Trades
from juno.components.prices import InsufficientPrices
from juno.exchanges import Binance, Exchange
from juno.logging import create_handlers
from juno.storages import SQLite

T = TypeVar("T")


async def juno(app: web.Application) -> AsyncIterator[None]:
    binance = Binance(
        api_key=os.environ["JUNO__BINANCE__API_KEY"],
        secret_key=os.environ["JUNO__BINANCE__SECRET_KEY"],
    )
    exchanges: list[Exchange] = [
        binance,
    ]
    storage = SQLite()
    trades = Trades(storage=storage, exchanges=exchanges)
    chandler = Chandler(storage=storage, exchanges=exchanges, trades=trades)
    informant = Informant(storage=storage, exchanges=exchanges)
    prices = Prices(informant=informant, chandler=chandler)
    async with binance, storage, trades, chandler, informant, prices:
        app["chandler"] = chandler
        app["trades"] = trades
        app["informant"] = informant
        app["prices"] = prices
        app["binance"] = binance
        yield


async def body(request: web.Request, type_: Type[T]) -> T:
    content_type = request.headers.get("Content-Type")
    if content_type is None or content_type == "*/*":
        content_type = "application/json"
    elif content_type not in {"application/json", "application/yaml"}:
        raise_bad_request_response(f"Unsupported Content-Type header: {content_type}")

    juno_content_type = request.headers.get("Juno-Content-Type")
    if juno_content_type is None:
        juno_content_type = "raw"
    elif juno_content_type not in {"raw", "config"}:
        raise_bad_request_response(f"Unsupported Juno-Content-Type header: {juno_content_type}")

    deserialize = yaml.load if content_type == "application/yaml" else json.loads
    juno_deserialize = (
        serialization.config.deserialize
        if juno_content_type == "config"
        else serialization.raw.deserialize
    )
    return juno_deserialize(deserialize(await request.text()), type_)


def response(request: web.Request, result: T, type_: Type[T]) -> web.Response:
    juno_accept = request.headers.get("Juno-Accept")
    if juno_accept is None:
        juno_accept = "raw"
    elif juno_accept not in {"raw", "config"}:
        raise_bad_request_response(f"Unsupported Juno-Accept header: {juno_accept}")

    accept = request.headers.get("Accept")
    if accept is None or accept == "*/*":
        accept = "application/json"
    elif accept not in {"application/json", "application/yaml"}:
        raise_bad_request_response(f"Unsupported Accept header: {accept}")

    juno_serialize = (
        serialization.config.serialize if juno_accept == "config" else serialization.raw.serialize
    )
    # We indent the response for easier debugging. Note that this is inefficient though.
    serialize = (
        partial(yaml.dump, indent=4)
        if accept == "application/yaml"
        else partial(json.dumps, indent=4)
    )
    return web.Response(
        text=serialize(juno_serialize(result, type_)),
        status=200,
        content_type=accept,
    )


def raise_bad_request_response(message: str) -> None:
    raise web.HTTPBadRequest(
        content_type="application/json",
        body=json.dumps(
            {
                "message": message,
            },
            indent=4,
        ),
    )


# Routing.

routes = web.RouteTableDef()


@routes.get("/")
async def hello(request: web.Request) -> web.Response:
    return web.Response(text="Hello, world")


class ExchangeRequest(TypedDict):
    exchange: str


@routes.post("/exchange_info")
async def exchange_info(request: web.Request) -> web.Response:
    payload = await body(request, ExchangeRequest)

    exchange: Optional[Exchange] = request.app.get(payload["exchange"])
    if exchange is None:
        raise web.HTTPBadRequest()

    result = await exchange.get_exchange_info()

    return response(request, result, ExchangeInfo)


class CandlesRequest(TypedDict):
    exchange: str
    symbol: str
    interval: Interval
    start: Timestamp
    end: Timestamp
    type_: CandleType


@routes.post("/candles")
async def candles(request: web.Request) -> web.Response:
    payload = await body(request, CandlesRequest)

    chandler: Chandler = request.app["chandler"]

    result = await chandler.list_candles(**payload)

    return response(request, result, list[Candle])


@routes.post("/candles_fill_missing_with_none")
async def candles_fill_missing_with_none(request: web.Request) -> web.Response:
    payload = await body(request, CandlesRequest)

    chandler: Chandler = request.app["chandler"]

    result = await chandler.list_candles_fill_missing_with_none(**payload)

    return response(request, result, list[Optional[Candle]])


@routes.post("/candle_intervals")
async def candle_intervals(request: web.Request) -> web.Response:
    payload = await body(request, ExchangeRequest)

    chandler: Chandler = request.app["chandler"]

    result = chandler.list_candle_intervals(**payload)

    return response(request, result, list[Interval])


class PricesRequest(TypedDict):
    exchange: str
    assets: list[Asset]
    interval: Interval
    start: Timestamp
    end: Timestamp
    target_asset: Asset


@routes.post("/prices")
async def prices(request: web.Request) -> web.Response:
    payload = await body(request, PricesRequest)

    prices: Prices = request.app["prices"]

    try:
        result = await prices.map_asset_prices(**payload)
    except InsufficientPrices as exc:
        raise_bad_request_response(str(exc))

    return response(request, result, dict[Asset, list[Decimal]])


# Main.

logging.basicConfig(
    handlers=create_handlers("color", ["stdout"], "api_logs"),
    level=logging.getLevelName("INFO"),
)

app = web.Application()
app.cleanup_ctx.append(juno)
app.add_routes(routes)

cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    },
)
for route in app.router.routes():
    cors.add(route)

web.run_app(app, port=3030)
