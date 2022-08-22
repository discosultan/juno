import logging
import os
from functools import partial
from typing import Any, AsyncIterator, Literal, Mapping

import aiohttp_cors
from aiohttp import web

from juno import json, serialization, yaml
from juno.components import Chandler, Informant, Prices, Trades
from juno.components.prices import InsufficientPrices
from juno.exchanges import Binance, Exchange
from juno.logging import create_handlers
from juno.storages import SQLite


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


async def json_body(request: web.Request, type_: Any) -> Any:
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


def json_response(request: web.Request, result: Any) -> web.Response:
    accept = request.headers.get("Accept")
    if accept is None or accept == "*/*":
        accept = "application/json"
    elif accept not in {"application/json", "application/yaml"}:
        raise_bad_request_response(f"Unsupported Accept header: {accept}")

    juno_accept = request.headers.get("Juno-Accept")
    if juno_accept is None:
        juno_accept = "raw"
    elif juno_accept not in {"raw", "config"}:
        raise_bad_request_response(f"Unsupported Juno-Accept header: {juno_accept}")

    # We indent the response for easier debugging. Note that this is inefficient though.
    serialize = (
        partial(yaml.dump, indent=4)
        if accept == "application/yaml"
        else partial(json.dumps, indent=4)
    )
    juno_serialize = (
        serialization.config.serialize if juno_accept == "config" else serialization.raw.serialize
    )
    return web.Response(
        text=serialize(juno_serialize(result)),
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


def query_get_candle_type(query: Mapping[str, str]) -> Literal["regular", "heikin-ashi"]:
    value = query.get("type")
    return "heikin-ashi" if value == "heikin-ashi" else "regular"


# Routing.

routes = web.RouteTableDef()


@routes.get("/")
async def hello(request: web.Request) -> web.Response:
    return web.Response(text="Hello, world")


@routes.get("/exchange_info")
async def exchange_info(request: web.Request) -> web.Response:
    binance: Binance = request.app["binance"]
    query = request.query

    exchange = query["exchange"]

    if exchange != "binance":
        raise web.HTTPBadRequest()

    result = await binance.get_exchange_info()

    return json_response(request, result)


@routes.get("/candles")
async def candles(request: web.Request) -> web.Response:
    chandler: Chandler = request.app["chandler"]
    query = request.query

    result = await chandler.list_candles(
        exchange=query["exchange"],
        symbol=query["symbol"],
        interval=int(query["interval"]),
        start=int(query["start"]),
        end=int(query["end"]),
        type_=query_get_candle_type(query),
    )

    return json_response(request, result)


@routes.get("/candles_fill_missing_with_none")
async def candles_fill_missing_with_none(request: web.Request) -> web.Response:
    chandler: Chandler = request.app["chandler"]
    query = request.query

    result = await chandler.list_candles_fill_missing_with_none(
        exchange=query["exchange"],
        symbol=query["symbol"],
        interval=int(query["interval"]),
        start=int(query["start"]),
        end=int(query["end"]),
        type_=query_get_candle_type(query),
    )

    return json_response(request, result)


@routes.get("/candle_intervals")
async def candle_intervals(request: web.Request) -> web.Response:
    chandler: Chandler = request.app["chandler"]
    query = request.query

    result = chandler.list_candle_intervals(
        exchange=query["exchange"],
    )

    return json_response(request, result)


@routes.get("/prices")
async def prices(request: web.Request) -> web.Response:
    prices: Prices = request.app["prices"]
    query = request.query

    try:
        result = await prices.map_asset_prices(
            exchange=query["exchange"],
            assets=query["assets"].split(","),
            interval=int(query["interval"]),
            start=int(query["start"]),
            end=int(query["end"]),
            target_asset=query["target_asset"],
        )
    except InsufficientPrices as exc:
        raise_bad_request_response(str(exc))

    return json_response(request, result)


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
