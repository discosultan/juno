from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiohttp

from .typing import ExcType, ExcValue, Traceback

_aiohttp_log = logging.getLogger('aiohttp.client')


# Adds logging to aiohttp client session.
# https://stackoverflow.com/a/45590516/1466456
# Note that aiohttp client session is not meant to be extended.
# https://github.com/aio-libs/aiohttp/issues/3185
class ClientSession:

    def __init__(self, **kwargs: Any) -> None:
        self._raise_for_status = kwargs.pop('raise_for_status', None)
        self._session = aiohttp.ClientSession(**kwargs)

    async def __aenter__(self) -> ClientSession:
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def request(self, method: str, url: str, **kwargs: Any
                      ) -> AsyncIterator[aiohttp.ClientResponse]:
        req = self._session.request(method, url, **kwargs)
        req_id = id(req)
        _aiohttp_log.info(f'Req {req_id} {method} {url}')
        _aiohttp_log.debug(kwargs)
        async with req as res:
            _aiohttp_log.info(f'Res {req_id} {res.status} {res.reason}')
            if res.status >= 400:
                _aiohttp_log.error(await res.text())
                if self._raise_for_status:
                    res.raise_for_status()
            else:
                _aiohttp_log.debug(await res.text())
            yield res

    @asynccontextmanager
    async def ws_connect(self, url: str, **kwargs: Any
                         ) -> AsyncIterator[_ClientWebSocketResponseWrapper]:
        _aiohttp_log.info(f'WS {url}')
        _aiohttp_log.debug(kwargs)
        async with self._session.ws_connect(url, **kwargs) as ws:
            yield _ClientWebSocketResponseWrapper(ws)


class _ClientWebSocketResponseWrapper:

    def __init__(self, client_ws_response: aiohttp.ClientWebSocketResponse) -> None:
        self._client_ws_response = client_ws_response

    def __aiter__(self) -> _ClientWebSocketResponseWrapper:
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        msg = await self._client_ws_response.__anext__()
        _aiohttp_log.debug(msg)
        return msg

    async def send_json(self, data: Any) -> None:
        _aiohttp_log.debug(data)
        await self._client_ws_response.send_json(data)
