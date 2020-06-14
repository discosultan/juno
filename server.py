import logging
from typing import AsyncIterator

from aiohttp import WSMsgType, web

_log = logging.getLogger(__file__)


async def juno(app: web.Application) -> AsyncIterator[None]:
    # Startup.
    yield
    # Cleanup.


async def hello(request: web.Request) -> web.Response:
    return web.Response(text='Hello, world')


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
            else:
                await ws.send_str(msg.data + '/answer')
        elif msg.type == WSMsgType.ERROR:
            _log.error(f'ws connection closed with exception {ws.exception()}')

    _log.info('websocket connection closed')

    return ws


app = web.Application()
app.cleanup_ctx.append(juno)
app.add_routes([
    web.get('/', hello),
    web.get('/ws', websocket_handler),
])

web.run_app(app, port=8080)
