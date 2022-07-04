import logging
import os
from typing import AsyncIterator

import aiohttp_cors
from aiohttp import web

from juno import json, serialization
from juno.components import Chandler
from juno.exchanges import Binance
from juno.logging import create_handlers
from juno.storages import SQLite


async def juno(app: web.Application) -> AsyncIterator[None]:
    exchange = Binance(
        api_key=os.environ["JUNO__BINANCE__API_KEY"],
        secret_key=os.environ["JUNO__BINANCE__SECRET_KEY"],
    )
    storage = SQLite()
    chandler = Chandler(storage=storage, exchanges=[exchange])
    async with exchange, storage, chandler:
        app["chandler"] = chandler
        yield


routes = web.RouteTableDef()


@routes.get("/")
async def hello(request: web.Request) -> web.Response:
    return web.Response(text="Hello, world")


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
    )

    return web.json_response(serialization.raw.serialize(result), dumps=json.dumps)


@routes.get("/candle_intervals")
async def candle_intervals(request: web.Request) -> web.Response:
    chandler: Chandler = request.app["chandler"]

    result = chandler.list_candle_intervals(
        exchange=request.query["exchange"],
    )

    return web.json_response(serialization.raw.serialize(result), dumps=json.dumps)


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
