import logging
import os
from functools import partial
from typing import Any, AsyncIterator, Literal, Mapping

import aiohttp_cors
from aiohttp import web

from juno import json, serialization
from juno.components import Chandler, Informant, Prices, Trades
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


def raw_json_response(result: Any) -> web.Response:
    # We indent the response for easier debugging. Note that this is inefficient though.
    return web.json_response(
        serialization.raw.serialize(result), dumps=partial(json.dumps, indent=4)
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

    return raw_json_response(result)


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

    return raw_json_response(result)


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

    return raw_json_response(result)


@routes.get("/candle_intervals")
async def candle_intervals(request: web.Request) -> web.Response:
    chandler: Chandler = request.app["chandler"]
    query = request.query

    result = chandler.list_candle_intervals(
        exchange=query["exchange"],
    )

    return raw_json_response(result)


@routes.get("/prices")
async def prices(request: web.Request) -> web.Response:
    prices: Prices = request.app["prices"]
    query = request.query

    result = await prices.map_asset_prices(
        exchange=query["exchange"],
        assets=query["assets"].split(","),
        interval=int(query["interval"]),
        start=int(query["start"]),
        end=int(query["end"]),
        target_asset=query["target_asset"],
    )

    return raw_json_response(result)


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
