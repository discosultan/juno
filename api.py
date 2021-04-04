import logging
import os
from typing import AsyncIterator

from aiohttp import web

import juno.json as json
from juno.asyncio import gather_dict
from juno.components import Chandler
from juno.exchanges import Binance
from juno.logging import create_handlers
from juno.storages import SQLite
from juno.time import strpinterval, strptimestamp


async def juno(app: web.Application) -> AsyncIterator[None]:
    exchange = Binance(
        api_key=os.environ['JUNO__BINANCE__API_KEY'],
        secret_key=os.environ['JUNO__BINANCE__SECRET_KEY'],
    )
    storage = SQLite()
    chandler = Chandler(storage=storage, exchanges=[exchange])
    async with exchange, storage, chandler:
        app['chandler'] = chandler
        yield


routes = web.RouteTableDef()


@routes.get('/')
async def hello(request: web.Request) -> web.Response:
    return web.Response(text='Hello, world')


@routes.post('/candles')
async def candles(request: web.Request) -> web.Response:
    chandler: Chandler = request.app['chandler']

    args = await request.json()
    interval = strpinterval(args['interval'])
    start = strptimestamp(args['start'])
    end = strptimestamp(args['end'])

    result = await gather_dict(
        {s: chandler.list_candles(
            exchange=args['exchange'],
            symbol=s,
            interval=interval,
            start=start,
            end=end,
        ) for s in args['symbols']}
    )

    return web.json_response(result, dumps=json.dumps)


logging.basicConfig(
    handlers=create_handlers('color', ['stdout'], 'api_logs'),
    level=logging.getLevelName('INFO'),
)

app = web.Application()
app.cleanup_ctx.append(juno)
app.add_routes(routes)

web.run_app(app)
