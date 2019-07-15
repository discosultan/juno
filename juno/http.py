from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterable, AsyncIterator, Callable, Optional

import aiohttp

from juno.utils import generate_random_words

from .asyncio import cancel, cancelable, concat_async
from .typing import ExcType, ExcValue, Traceback

_aiohttp_log = logging.getLogger('aiohttp.client')

_random_words = generate_random_words(length=6)


# Adds logging to aiohttp client session.
# https://stackoverflow.com/a/45590516/1466456
# Note that aiohttp client session is not meant to be extended.
# https://github.com/aio-libs/aiohttp/issues/3185
class ClientSession:
    def __init__(self, raise_for_status: Optional[bool] = None, **kwargs: Any) -> None:
        self._raise_for_status = raise_for_status
        self._session = aiohttp.ClientSession(**kwargs)

    async def __aenter__(self) -> ClientSession:
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def request(
        self, method: str, url: str, raise_for_status: Optional[bool] = None, **kwargs: Any
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        req = self._session.request(method, url, **kwargs)
        req_id = next(_random_words)
        _aiohttp_log.info(f'Req {req_id} {method} {url}')
        _aiohttp_log.debug(kwargs)
        async with req as res:
            _aiohttp_log.info(f'Res {req_id} {res.status} {res.reason}')
            content = {'headers': res.headers, 'body': await res.text()}
            _aiohttp_log.debug(content)
            if raise_for_status or (raise_for_status is None and self._raise_for_status):
                res.raise_for_status()
            yield res

    @asynccontextmanager
    async def ws_connect(self, url: str, **kwargs: Any) -> AsyncIterator[ClientWebSocketResponse]:
        ws_id = next(_random_words)
        _aiohttp_log.info(f'WS {ws_id} {url}')
        _aiohttp_log.debug(kwargs)
        async with self._session.ws_connect(url, **kwargs) as ws:
            yield ClientWebSocketResponse(ws, ws_id)


class ClientWebSocketResponse:
    def __init__(self, client_ws_response: aiohttp.ClientWebSocketResponse, ws_id: str) -> None:
        self._client_ws_response = client_ws_response
        self._ws_id = ws_id

    def __aiter__(self) -> ClientWebSocketResponse:
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        msg = await self._client_ws_response.__anext__()
        _aiohttp_log.debug(f'{self._ws_id} {msg}')
        return msg

    async def send_json(self, data: Any) -> None:
        _aiohttp_log.debug(f'{self._ws_id} {data}')
        await self._client_ws_response.send_json(data)

    async def close(self) -> None:
        await self._client_ws_response.close()

    async def receive(self) -> aiohttp.WSMessage:
        msg = await self._client_ws_response.receive()
        _aiohttp_log.debug(f'{self._ws_id} {msg}')
        return msg


@asynccontextmanager
async def connect_refreshing_stream(
    session: ClientSession, url: str, interval: int, loads: Callable[[str], Any],
    take_until: Callable[[Any, Any], bool]
) -> AsyncIterator[AsyncIterable[Any]]:
    """Streams messages over WebSocket. The connection is restarted every `interval` milliseconds.
    Ensures no data is lost during restart when switching from one connection to another.
    """
    conn = session.ws_connect(url)
    ws = await conn.__aenter__()

    async def inner() -> AsyncIterable[Any]:
        nonlocal conn, ws
        try:
            while True:
                to_close_conn = None
                to_close_ws = None
                timeout_task = asyncio.create_task(cancelable(asyncio.sleep(interval)))
                while True:
                    receive_task = asyncio.create_task(cancelable(_receive(ws)))
                    done, _pending = await asyncio.wait([receive_task, timeout_task],
                                                        return_when=asyncio.FIRST_COMPLETED)

                    if timeout_task in done:
                        _aiohttp_log.info('refreshing ws connection')
                        to_close_conn = conn
                        to_close_ws = ws
                        conn = session.ws_connect(url)
                        ws = await conn.__aenter__()

                        if receive_task.done():
                            new_msg = await _receive(ws)
                            assert new_msg.type is aiohttp.WSMsgType.TEXT
                            new_data = loads(new_msg.data)
                            async for old_msg in concat_async(receive_task.result(), to_close_ws):
                                if old_msg.type is aiohttp.WSMsgType.CLOSED:
                                    break
                                old_data = loads(old_msg.data)
                                if take_until(old_data, new_data):
                                    yield old_data
                                else:
                                    break
                            yield new_data

                        await to_close_ws.close()
                        await to_close_conn.__aexit__(None, None, None)
                        break

                    msg = receive_task.result()
                    if msg.type is aiohttp.WSMsgType.CLOSED:
                        _aiohttp_log.warning(f'server closed connection: {msg.data}; reconnecting')
                        await asyncio.gather(
                            conn.__aexit__(None, None, None), cancel(timeout_task)
                        )
                        conn = session.ws_connect(url)
                        ws = await conn.__aenter__()
                        break

                    yield loads(msg.data)
        except asyncio.CancelledError:
            await cancel(receive_task, timeout_task)
            raise

    try:
        yield inner()
    finally:
        await ws.close()
        await conn.__aexit__(None, None, None)


async def _receive(ws: ClientWebSocketResponse) -> aiohttp.WSMessage:
    while True:
        msg = await ws.receive()
        if msg.type in [aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.CLOSED]:
            return msg
        # Ping is handled implicitly by aiohttp because `autoping=True`. It will never reach here.
        # Close is handled implicitly by aiohttp because `autoclose=True`. It will reach here.
        if msg.type in [aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSE]:
            continue
        raise NotImplementedError(f'Unhandled WS message. Type: {msg.type}; data: {msg.data}')
